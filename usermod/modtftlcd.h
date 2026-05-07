#ifndef __MODTFTLCD_H
#define __MODTFTLCD_H

#ifdef __cplusplus
 extern "C" {
#endif 

#include "py/obj.h"
#include "py/stream.h"

// Color Definitions
#define WHITE         	 	0xFFFF
#define BLACK         	 	0x0000	  
#define BLUE         	 	0x001F  
#define RED           	 	0xF800
#define GREEN         	 	0x07E0

typedef struct  
{		 	 
	volatile uint16_t width;
	volatile uint16_t height;
	volatile uint16_t id;
	volatile uint8_t  dir;
	volatile uint8_t  type;				
	volatile uint16_t backcolor; 
	volatile uint16_t clercolor; 
	volatile uint16_t x_pixel;
	volatile uint16_t y_pixel;
}_lcd_dev;

extern _lcd_dev lcddev;

typedef struct
{
	uint8_t scan;
	uint8_t gray;
	uint16_t w;
	uint16_t h;
	uint8_t is565;
	uint8_t rgb;
}__attribute__((packed)) IMAGE2LCD; 

typedef struct
{
	uint8_t color_depth; 
	volatile uint16_t width;
	volatile uint16_t height;
	void (*callDrawPoint)(uint16_t x, uint16_t y,uint16_t color);
	uint16_t (*callReadPoint)(uint16_t x, uint16_t y);
	void (*callDrawhline)(uint16_t x,uint16_t y,uint16_t len,uint16_t color);
	void (*callDrawvline)(uint16_t x,uint16_t y,uint16_t len,uint16_t color);
	void (*callDrawFill)(uint16_t sx,uint16_t sy,uint16_t ex,uint16_t ey,uint16_t color);
	void (*callDrawFlush)(uint16_t sx,uint16_t sy,uint16_t ex,uint16_t ey,uint16_t *color);
	void (*callDrawCam)(uint16_t sx,uint16_t sy,uint16_t ex,uint16_t ey,uint16_t *color);
} Graphics_Display;

extern void grap_drawInit(uint16_t width, uint16_t height);
extern void grap_drawLine(const Graphics_Display *display, uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t color);
extern void grap_drawRect(const Graphics_Display *display, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t border, uint16_t color);
extern void grap_drawColorCircle(const Graphics_Display *display, uint16_t x, uint16_t y, uint16_t r, uint16_t color);
extern void grap_drawChar(const Graphics_Display *display, uint16_t x,uint16_t y,uint8_t num, uint8_t size,uint16_t color,uint16_t backcolor);
extern void grap_drawStr(const Graphics_Display *display, uint16_t x,uint16_t y,uint16_t width,uint16_t height, uint8_t size, char *p , uint16_t color,uint16_t backcolor);
extern Graphics_Display * draw_global;
extern void grap_drawCam(uint16_t x,uint16_t y,uint16_t width,uint16_t height,uint16_t *color);
extern void grap_drawFull(uint16_t x,uint16_t y,uint16_t width,uint16_t height,uint16_t *color);
extern void grap_drawFill(uint16_t x,uint16_t y,uint16_t width,uint16_t height,uint16_t color);

extern uint8_t grap_drawCached(const Graphics_Display *display, void *fs, uint16_t x, uint16_t y, const char *filename);
extern uint8_t grap_newCached(const Graphics_Display *display, mp_obj_t stream ,const char *filename, uint16_t width, uint16_t height);

#ifdef __cplusplus
}
#endif

#endif