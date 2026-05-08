/**
	******************************************************************************
	* Copyright (C), 2021 -2023, 01studio Tech. Co., Ltd.https://www.01studio.cc/
	* File Name					:	psxcontroller.c
	* Author					:	Folktale
	* Version					:	v1.0
	* date						:	2021/7/1
	* Description				:	Updated for ESP-IDF v5 compatability
	******************************************************************************
**/

#include "mpconfigboard.h"
#include "esp_system.h"
#include "py/obj.h"
#include <math.h>
#include "py/builtin.h"
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

#include "py/binary.h"
#include "py/objarray.h"
#include "py/mperrno.h"

#include <stdio.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "freertos/queue.h"
#include "driver/gpio.h"
#include "psxcontroller.h"

#if MICROPY_ENABLE_PSXCONTROLLER

// Replaced deprecated driver/adc.h with new oneshot API for ESP-IDF v5
#include "esp_adc/adc_oneshot.h"
#include "hal/adc_types.h"
#include "esp_log.h"

#include "py/runtime.h"
#include "py/mphal.h"
#include "modmachine.h"

#define GPIO_PULL_DOWN (1)
#define GPIO_PULL_UP   (2)
#define GPIO_PULL_HOLD (4)

#define ADC_EXAMPLE_ATTEN ADC_ATTEN_DB_0
#define NO_OF_SAMPLES	10

static bool is_initpsx = 0;

// Handle for the new Oneshot ADC unit
static adc_oneshot_unit_handle_t adc1_handle;

static void joy_gpio_init(void)
{
    // Initialize the ADC Unit
    adc_oneshot_unit_init_cfg_t init_config1 = {
        .unit_id = ADC_UNIT_1,
    };
    esp_err_t err = adc_oneshot_new_unit(&init_config1, &adc1_handle);
    if (err != ESP_OK) {
        printf("PSX ADC Unit 1 init error\r\n");
        return;
    }

    // Configure the channels
    adc_oneshot_chan_cfg_t config = {
        .bitwidth = ADC_BITWIDTH_DEFAULT,
        .atten = ADC_EXAMPLE_ATTEN,
    };

    adc_oneshot_config_channel(adc1_handle, PSX_ADCL_LEFTRIGHT_CH, &config);
    adc_oneshot_config_channel(adc1_handle, PSX_ADCL_UPDOWN_CH, &config);
    adc_oneshot_config_channel(adc1_handle, PSX_ADCR_LEFTRIGHT_CH, &config);
    adc_oneshot_config_channel(adc1_handle, PSX_ADCR_UPDOWN_CH, &config);
}

static void gpio_global_init(gpio_num_t gpio, gpio_mode_t io_mode, uint8_t mode)
{
    // Replaced deprecated gpio_pad_select_gpio with gpio_reset_pin
    gpio_reset_pin(gpio);
    gpio_set_direction(gpio, io_mode);
    
    if (mode & GPIO_PULL_DOWN) {
        gpio_pulldown_en(gpio);
    } else {
        gpio_pulldown_dis(gpio);
    }
    if (mode & GPIO_PULL_UP) {
        gpio_pullup_en(gpio);
    } else {
        gpio_pullup_dis(gpio);
    }
    if (mode & GPIO_PULL_HOLD) {
        gpio_hold_en(gpio);
    } else if (GPIO_IS_VALID_OUTPUT_GPIO(gpio)) {
        gpio_hold_dis(gpio);
    }
}

static void input_gpio_init(void)
{
    gpio_global_init(PSX_GPIO_UP, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_DOWN, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_LEFT, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_RIGHT, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_X, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_Y, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_A, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_B, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_BACK, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_START, GPIO_MODE_INPUT, GPIO_PULL_UP);
    
    gpio_global_init(PSX_GPIO_A_OK, GPIO_MODE_INPUT, GPIO_PULL_UP);
    gpio_global_init(PSX_GPIO_B_OK, GPIO_MODE_INPUT, GPIO_PULL_UP);
}

static void joy_adc_read(uint16_t *joy_leftright, uint16_t *joy_updown)
{	
    int adc_reading1 = 0;
    int adc_reading2 = 0;
    int raw_val;

    for (int i = 0; i < NO_OF_SAMPLES; i++) {
        adc_oneshot_read(adc1_handle, PSX_ADCL_LEFTRIGHT_CH, &raw_val);
        adc_reading1 += raw_val;
        adc_oneshot_read(adc1_handle, PSX_ADCL_UPDOWN_CH, &raw_val);
        adc_reading2 += raw_val;
    }
    
    *joy_leftright = (uint16_t)(adc_reading1 / NO_OF_SAMPLES);
    *joy_updown = (uint16_t)(adc_reading2 / NO_OF_SAMPLES);
}

void gamepad_get_adc(uint16_t *leftX, uint16_t *leftY, uint16_t *rightX, uint16_t *rightY)
{
    int adc_reading1 = 0;
    int adc_reading2 = 0;
    int adc_reading3 = 0;
    int adc_reading4 = 0;
    int raw_val;

    for (int i = 0; i < NO_OF_SAMPLES; i++) {
        adc_oneshot_read(adc1_handle, PSX_ADCL_LEFTRIGHT_CH, &raw_val);
        adc_reading1 += raw_val;
        
        adc_oneshot_read(adc1_handle, PSX_ADCL_UPDOWN_CH, &raw_val);
        adc_reading2 += raw_val;
        
        adc_oneshot_read(adc1_handle, PSX_ADCR_LEFTRIGHT_CH, &raw_val);
        adc_reading3 += raw_val;
        
        adc_oneshot_read(adc1_handle, PSX_ADCR_UPDOWN_CH, &raw_val);
        adc_reading4 += raw_val;
    }
    
    *leftX = (uint16_t)(adc_reading1 / NO_OF_SAMPLES);
    *leftY = (uint16_t)(adc_reading2 / NO_OF_SAMPLES);
    *rightX = (uint16_t)(adc_reading3 / NO_OF_SAMPLES);
    *rightY = (uint16_t)(adc_reading4 / NO_OF_SAMPLES);
}

void gamepad_get_key(uint8_t *keyByte5, uint8_t *keyByte6)
{
    uint8_t key5 = 0, key6 = 0;
    bool up = 0, down = 0, left = 0, right = 0;

    if(PSX_UP_PRESSED == gpio_get_level(PSX_GPIO_UP)){
        up = 1;
    }
    if(PSX_RIGHT_PRESSED == gpio_get_level(PSX_GPIO_RIGHT)){
        right = 1;
    }
    if(PSX_DOWN_PRESSED == gpio_get_level(PSX_GPIO_DOWN)){
        down = 1;
    }
    if(PSX_LEFT_PRESSED == gpio_get_level(PSX_GPIO_LEFT)){
        left = 1;
    }
    
    if(up){
        if(right)		key5 = 1;
        else if(left)	key5 = 7;
        else			key5 = 0;
    }else if(down){
        if(right)		key5 = 3;
        else if(left)	key5 = 5;
        else			key5 = 4;
    }else if(right){
        key5 = 2;
    }else if(left){
        key5 = 6;
    }else{
        key5 = 8;
    }

    if(PSX_A_PRESSED == gpio_get_level(PSX_GPIO_A)){
        key5 |= (1<<6);
    }
    if(PSX_B_PRESSED == gpio_get_level(PSX_GPIO_B)){
        key5 |= (1<<5);
    }
    if(PSX_X_PRESSED == gpio_get_level(PSX_GPIO_X)){
        key5 |= (1<<7);
    }
    if(PSX_Y_PRESSED == gpio_get_level(PSX_GPIO_Y)){
        key5 |= (1<<4);
    }
    if(PSX_BACK_PRESSED == gpio_get_level(PSX_GPIO_BACK)){
        key6 |= (1<<4);
    }
    if(PSX_START_PRESSED == gpio_get_level(PSX_GPIO_START)){
        key6 |= (1<<5);
    }
    if(PSX_AOK_PRESSED == gpio_get_level(PSX_GPIO_A_OK)){
        key6 |= (1<<7);
    }
    if(PSX_BOK_PRESSED == gpio_get_level(PSX_GPIO_B_OK)){
        key6 |= (1<<6);
    }
    
    *keyByte5 = key5;
    *keyByte6 = key6;
}

static int joy_read_data(void)
{
    int pxsInput = 0xffff;
    uint16_t leftright_voltage=0, updown_voltage=0;
    uint8_t lr_dir = 0, ud_dir = 0;
    
    joy_adc_read(&leftright_voltage, &updown_voltage);

    if(leftright_voltage >= PSX_JOY_RIGHT_VALUE){
        lr_dir = 1;  //right
    }else if(leftright_voltage <= PSX_JOY_LEFT_VALUE){
        lr_dir = 2; //left
    }
    
    if(updown_voltage >= PSX_JOY_UP_VALUE){
        ud_dir = 1; //up
    }else if(updown_voltage <= PSX_JOY_DOWN_VALUE){
        ud_dir = 2; //down
    }
    
    //up1
    if(PSX_UP_PRESSED == gpio_get_level(PSX_GPIO_UP) || ud_dir == 1){
        pxsInput &= ~(1<<15);
    }
    //down1
    if(PSX_DOWN_PRESSED == gpio_get_level(PSX_GPIO_DOWN) || ud_dir == 2){
        pxsInput &= ~(1<<14);
    }
    //right1
    if(PSX_RIGHT_PRESSED == gpio_get_level(PSX_GPIO_RIGHT) || lr_dir == 1){
        pxsInput &= ~(1<<12);
    }
    //left1
    if(PSX_LEFT_PRESSED == gpio_get_level(PSX_GPIO_LEFT) || lr_dir == 2){
        pxsInput &= ~(1<<13);
    }
    if(PSX_A_PRESSED == gpio_get_level(PSX_GPIO_A)){
        pxsInput &= ~(1<<11);
    }
    if(PSX_B_PRESSED == gpio_get_level(PSX_GPIO_B)){
        pxsInput &= ~(1<<10);
    }
    if(PSX_X_PRESSED == gpio_get_level(PSX_GPIO_X)){
        pxsInput &= ~(1<<9);
    }
    if(PSX_Y_PRESSED == gpio_get_level(PSX_GPIO_Y)){
        pxsInput &= ~(1<<8);
    }
    if(PSX_BACK_PRESSED == gpio_get_level(PSX_GPIO_BACK)){
        pxsInput &= ~(1<<7);
    }
    if(PSX_START_PRESSED == gpio_get_level(PSX_GPIO_START)){
        pxsInput &= ~(1<<6);
    }

    return pxsInput;
}

int psxReadInput() {
    return joy_read_data();
}

void psxcontrollerInit() {
    if(!is_initpsx){
        input_gpio_init();
        joy_gpio_init();
        is_initpsx = 1;
    }
}

#else
int psxReadInput() {
    return 0xFFFF;
}
void psxcontrollerInit() {

}

#endif