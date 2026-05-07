/********************************************************************************
	* Copyright (C), 2022 -2023, 01studio Tech. Co., Ltd.https://www.01studio.cc/
	* File Name				:	modtftlcd.c
	* Author				:	Folktale
	* Version				:	v1.0
	* date					:	2022/3/25
	* Description			:	
******************************************************************************/

#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "py/runtime.h"
#include "py/mphal.h"
#include "shared/runtime/pyexec.h"
#include "mpconfigboard.h"
#include "modmachine.h"
#include "extmod/vfs.h"
// #include "extmod/utime_mphal.h"
#include "py/obj.h"
#include "py/builtin.h"
#include "py/stream.h"

// Removed conditional wrappers around includes so the QSTR extractor can read the file
#include "ILI9341.h"
#include "ST7789.h"
#include "ST7735.h"

#include "modtftlcd.h"
#include "font.h"

_lcd_dev lcddev;

Graphics_Display * draw_global = NULL;

void grap_drawLine(const Graphics_Display *display, uint16_t x1, uint16_t y1, uint16_t x2, uint16_t y2, uint16_t color)
{
	uint16_t t; 
	int xerr=0,yerr=0,delta_x,delta_y,distance; 
	int incx,incy,uRow,uCol; 
	delta_x=x2-x1; 
	delta_y=y2-y1; 
	uRow=x1; 
	uCol=y1; 
	if(delta_x>0)incx=1; 
	else if(delta_x==0)incx=0;
	else {incx=-1;delta_x=-delta_x;} 
	if(delta_y>0)incy=1; 
	else if(delta_y==0)incy=0;
	else{incy=-1;delta_y=-delta_y;} 
	if( delta_x>delta_y)distance=delta_x; 
	else distance=delta_y; 
	for(t=0;t<=distance+1;t++ )
	{  
		display->callDrawPoint(uRow, uCol, color);
		xerr+=delta_x ; 
		yerr+=delta_y ; 
		if(xerr>distance) 
		{ 
			xerr-=distance; 
			uRow+=incx; 
		} 
		if(yerr>distance) 
		{ 
			yerr-=distance; 
			uCol+=incy; 
		} 
	} 
}

void grap_drawRect(const Graphics_Display *display, uint16_t x, uint16_t y, uint16_t width, uint16_t height, uint16_t border, uint16_t color)
{
	for(uint16_t i=0 ; i < border; i++ )
	{
		grap_drawLine(display, x,   y+i, x+width, y+i,  color);
		grap_drawLine(display, x+i, y, x+i, y+height, color);
		grap_drawLine(display, x, y+height-i ,x+width, y+height-i, color);
		grap_drawLine(display, x+width-i, y, x+width-i, y+height, color);
	}
}

/**
 * @breif	带颜色画圆函数
 * @param   x1,x2 —— 圆心坐标
 * @param	r —— 半径
 * @param	color —— 颜色
 * @retval	none
 *
 */

void grap_drawColorCircle(const Graphics_Display *display,
												uint16_t x, uint16_t y, uint16_t r, uint16_t color)
{

  int16_t a = 0, b = r;
  //int16_t d = 3 - (r << 1);
	uint16_t net_r = 0;

	net_r = r;
	if((x - r) < 0){
		net_r = x;
	}else if((x+r) > display->width){
		net_r = display->width - x;
	}
	
	if((y - net_r) < 0){
		net_r = y;
	}else if((y+net_r) > display->height){
		net_r = display->height - y;
	}	
	
	/* 如果圆在屏幕可见区域外，直接退出 */
	if (x - net_r < 0 || x + net_r > display->width || y - net_r < 0 || y + net_r > display->height) 
	{
		return;
	}
	int16_t d = 3 - (net_r << 1);

	/* 开始画圆 */
	while(a<=b){
		display->callDrawPoint(x+a, y-b, color); //1
		display->callDrawPoint(x+b, y-a, color);
		display->callDrawPoint(x+b, y+a, color); //2
		display->callDrawPoint(x+a, y+b, color);
		display->callDrawPoint(x-a, y+b, color); //3
		display->callDrawPoint(x-b, y+a, color);

		display->callDrawPoint(x-a, y-b, color); //4
		display->callDrawPoint(x-b, y-a, color);
		a++;
		//使用Bresenham算法画圆
		if(d<0){
			d += (a<<2) + 6;
		}else{
			d += 10 + ((a - b)<<2);
			b--;
		}
	}
}

//------------------------------------------------------------------------------------------------------
#define BUF_LEN 1160
static uint16_t str_buf[BUF_LEN]={0};//申请最大字体内存
void grap_drawChar(const Graphics_Display *display, uint16_t x,uint16_t y,uint8_t num,
											uint8_t size,uint16_t color,uint16_t backcolor)
{

	uint8_t temp,t1,t;
	uint16_t y0=0,x0=0;;
	uint16_t str_h,str_w;
	//得到字体一个字符对应点阵集所占的字节数
	uint16_t csize=((size>>3)+((size%8)?1:0))*(size>>1);		
 	num=num-' ';//得到偏移后的值（ASCII字库是从空格开始取模，所以-' '就是对应字符的字库）

	str_h = size; 
	str_w = size>>1;

	for(t=0;t<csize;t++)
	{
		
		if(0){
		#if MICROPY_STRING_SIZE_24
		}else if(size==24){
			temp=asc2_2412[num][t];
		#endif
		#if MICROPY_STRING_SIZE_32
		}else if(size==32){
			temp=asc2_3216[num][t];	
		#endif
		#if MICROPY_STRING_SIZE_48
		}else if(size==48){
			temp=asc2_4824[num][t];
		#endif
		}else{
			temp=asc2_1608[num][t];
		}
		for(t1=0;t1<8;t1++)
		{
			if(temp&0x80){
				str_buf[str_w * y0 + x0] = color;
			}else{
				str_buf[str_w * y0 + x0] = backcolor;
			}
			y0++;
			if(y0 >= size){
				y0 = 0;
				x0++;
			}
			temp<<=1;
		}  	 
	}
	display->callDrawFlush(x,y,str_w,str_h,str_buf);

}

void grap_drawStr(const Graphics_Display *display, uint16_t x,uint16_t y,uint16_t width,uint16_t height,
									uint8_t size, char *p , uint16_t color,uint16_t backcolor)
{         
	uint8_t x0=x;
	width+=x;
	height+=y;
	while((*p<='~')&&(*p>=' '))//判断是不是非法字符!
	{       
		if(x>=width)
		{
			x=x0;
			y+=size;
		}
		if(y>=height)break;//退出

		grap_drawChar(display,x,y,*p,size,color, backcolor);
		x+=(size>>1);
		p++;
	}  
}

void grap_drawCam(uint16_t x,uint16_t y,uint16_t width,uint16_t height,uint16_t *color)
{
	if(draw_global == NULL){
		printf("draw_global is null\r\n");
		return;
	}
	draw_global->callDrawCam(x,y,width,height,color);
}
void grap_drawFull(uint16_t x,uint16_t y,uint16_t width,uint16_t height,uint16_t *color)
{
	if(draw_global == NULL){
		printf("draw_global is null\r\n");
		return;
	}
	draw_global->callDrawFlush(x,y,width,height,color);
}
void grap_drawFill(uint16_t x,uint16_t y,uint16_t width,uint16_t height,uint16_t color)
{
	// if(draw_global == NULL){
		// printf("draw_global is null\r\n");
		// return;
	// }
	draw_global->callDrawFill(x,y,width,height,color);
}
//------------------------------------------------------------------------------------------------------

//显示成功返回0，其他失败
uint8_t grap_drawCached(const Graphics_Display *display,
								void *fs, uint16_t x, uint16_t y, const char *filename)
{
	uint16_t i=0;
	uint32_t readlen = 0;
	uint8_t *databuf;    		//数据读取存 
	uint8_t *hardbuf;    		//数据读取存 

	uint16_t rowcnt = 10;				//一次读取的行数
	uint16_t vp_line;	  		 	//垂直整数倍
	uint16_t vp_dot;	  		 	//垂直余数倍
	
	IMAGE2LCD *image2lcd;
	uint16_t display_w,display_h;
	uint16_t *d_color;
	
	hardbuf=(uint8_t*)m_malloc(8);