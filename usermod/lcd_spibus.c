/********************************************************************************
 * Copyright (C), 2021 - 2022, 01studio Tech. Co., Ltd.https://www.01studio.cc/
 * File Name				:	lcd_spibus.c (Modified for pyController & ESP-IDFv5)
 * Author				:	Folktale
 * Version				:	v1.1
 * date					:	2021/9/22
 * Description			:	
 ******************************************************************************/

#include "mpconfigboard.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "esp_system.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "driver/rtc_io.h"

#include "py/obj.h"
#include <math.h>
#include "py/builtin.h"
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>
#include "py/runtime.h"
#include "py/stream.h"
#include "py/mphal.h"
#include "modmachine.h"

#include "py/binary.h"
#include "py/objarray.h"
#include "py/mperrno.h"
#include "extmod/vfs.h"
#include "py/stream.h"
#include "shared/runtime/pyexec.h"

#if (MICROPY_ENABLE_TFTLCD)
#include "lcd_spibus.h"

#ifdef CONFIG_IDF_TARGET_ESP32
#define SPI_DMA_CH	2
#define LCD_HOST    HSPI_HOST
#elif defined CONFIG_IDF_TARGET_ESP32S2
#define LCD_HOST    SPI2_HOST
#define SPI_DMA_CH	3
#elif defined CONFIG_IDF_TARGET_ESP32C3
#define LCD_HOST    	SPI2_HOST
#define SPI_DMA_CH		SPI_DMA_CH_AUTO
#elif defined CONFIG_IDF_TARGET_ESP32S3
#define LCD_HOST    SPI2_HOST
#define SPI_DMA_CH	SPI_DMA_CH_AUTO
#else
#error Target CONFIG_IDF_TARGET is not supported
#endif

lcd_spibus_t *lcd_spibus = NULL;

static bool is_init = 0;

static void lcd_global_init(gpio_num_t gpio,gpio_mode_t io_mode)
{
	if (rtc_gpio_is_valid_gpio(gpio)) {
		rtc_gpio_deinit(gpio);
	}

    // This is the modern ESP-IDF v5 replacement for gpio_pad_select_gpio
	gpio_reset_pin(gpio);
	gpio_set_direction(gpio, io_mode);
	gpio_pulldown_dis(gpio);
	gpio_pullup_dis(gpio); // Most LCDs don't need pullups on control lines

	if (GPIO_IS_VALID_OUTPUT_GPIO(gpio)) {
		gpio_hold_dis(gpio);
	}
}

uint16_t get_rgb565(uint8_t r_color, uint8_t g_color , uint8_t b_color)
{
	uint16_t B_color = (b_color >> 3) & 0x001F;
	uint16_t G_color = ((g_color >> 2) << 5) & 0x07E0;
	uint16_t R_color = ((r_color >> 3) << 11) & 0xF800;

	return (uint16_t) (R_color | G_color | B_color);
}

static void lcd_spibus_init(lcd_spibus_t *self)
{
	esp_err_t ret;
	spi_bus_config_t buscfg={
		.miso_io_num=self->miso,
		.mosi_io_num=self->mosi,
		.sclk_io_num=self->clk,
		.quadwp_io_num=-1,
		.quadhd_io_num=-1,
		#if CONFIG_ESP32_SPIRAM_SUPPORT || CONFIG_ESP32S2_SPIRAM_SUPPORT || CONFIG_ESP32S3_SPIRAM_SUPPORT
		.max_transfer_sz=2*240*240+10,
		#else
		.max_transfer_sz=11*1024,
		#endif
	};

	spi_device_interface_config_t devcfg={
		.clock_speed_hz=self->mhz*1000*1000,
		.mode=0,                             //SPI mode 0
		.spics_io_num=self->cs,              //CS pin
		.queue_size=7,
		.flags=SPI_DEVICE_HALFDUPLEX,
	};

	ret=spi_bus_initialize(self->spihost, &buscfg, SPI_DMA_CH);
	if (ret != ESP_OK){
		mp_raise_ValueError(MP_ERROR_TEXT("lcd Failed initializing SPI bus"));
	}
	ret=spi_bus_add_device(self->spihost, &devcfg, &self->spi);
	if (ret != ESP_OK){
		mp_raise_ValueError(MP_ERROR_TEXT("lcd Failed adding SPI device"));
	}
}

void lcd_spibus_send(lcd_spibus_t *self, const uint8_t * data, uint32_t length)
{
	if (length == 0) return;

	spi_transaction_t t;
	memset(&t, 0, sizeof(t));
	t.length = length * 8;
	t.tx_buffer = data;

	spi_device_transmit(self->spi, &t);
}

void lcd_spibus_fill(lcd_spibus_t *self, uint16_t data, uint32_t length)
{
	if (length == 0) return;

	gpio_set_level(self->dc, 1);

	uint8_t *t_data = (uint8_t *)m_malloc(length*2);
	if(t_data == NULL){
		printf("fill malloc error\r\n");
        return;
	}
	for(uint32_t i=0; i < length; i++){
		t_data[2*i] = (data >> 8);
		t_data[2*i+1] = (data & 0xFF);
	}

	spi_transaction_t t;
	memset(&t, 0, sizeof(t));
	t.length = length * 8 *2;
	t.tx_buffer = t_data;

	spi_device_transmit(self->spi, &t);
	
	m_free(t_data);
}

void lcd_spibus_send_cmd(lcd_spibus_t *self, uint8_t cmd)
{
	gpio_set_level(self->dc, 0);
	lcd_spibus_send(self, &cmd, 1);
}

void lcd_spibus_send_data(lcd_spibus_t *self, const void * data, uint32_t length)
{
	gpio_set_level(self->dc, 1);
	lcd_spibus_send(self, data, length);
}

void  lcd_bus_init(void)
{
	if(!is_init)
	{
		lcd_spibus = (lcd_spibus_t *)m_malloc(sizeof(lcd_spibus_t));
		if(lcd_spibus == NULL){
			printf("lcd_spibus is NULL\r\n");
            return;
		}
		lcd_spibus_t *self = lcd_spibus;
		self->mhz			= 50; // ESP32-S3 can handle high speeds
		self->spi 		    = NULL;
		self->spihost	    = LCD_HOST;
        
        // --- Pins hardcoded from pyController v1.0 schematic ---
		self->miso 		= -1;     // Schematic does not show MISO connected
		self->mosi 		= 41;     // SDA
		self->clk  		= 40;     // SCL
		self->cs   		= 39;     // CS
		self->dc   		= 38;     // D/C
		self->rst  		= 42;     // RST
        // ----------------------------------------------------

		lcd_spibus_init(self);
		
		lcd_global_init(self->dc, GPIO_MODE_OUTPUT);
		lcd_global_init(self->rst, GPIO_MODE_OUTPUT);
		
		//Reset the display
		gpio_set_level(self->rst, 0);
        // Modern FreeRTOS replacement for portTICK_RATE_MS
		vTaskDelay(100 / portTICK_PERIOD_MS);
		gpio_set_level(self->rst, 1);
		vTaskDelay(100 / portTICK_PERIOD_MS);
		
		is_init = 1;
	}
}

void lcd_spibus_deinit(void) {
	if(is_init){
		if (lcd_spibus->spi) {
            spi_bus_remove_device(lcd_spibus->spi);
            spi_bus_free(lcd_spibus->spihost);
        }

		int8_t pins[] = {lcd_spibus->mosi, lcd_spibus->clk, lcd_spibus->cs, lcd_spibus->dc, lcd_spibus->rst};
		for (int i = 0; i < 5; i++) {
			if (pins[i] != -1) {
				gpio_reset_pin(pins[i]);
			}
		}
		is_init = 0;
		m_free(lcd_spibus);
        lcd_spibus = NULL;
	}
}

#endif // MICROPY_ENABLE_TFTLCD