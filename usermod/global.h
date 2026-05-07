/**
 ******************************************************************************
 * Copyright (C), 2021 -2023, 01studio Tech. Co., Ltd.
 * File Name : global.h
 * Author    : Folktale
 * Version   : v1.0
 * date      : 2021/3/23
 ******************************************************************************
 **/

#ifndef __GLOBAL_H
#define __GLOBAL_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <stdlib.h>
#include <stdarg.h>

#include "extmod/vfs.h"
#include "extmod/vfs_fat.h"
#include "py/mperrno.h"
#include "py/runtime.h"
#include "py/obj.h"
#include "py/stream.h"

extern mp_obj_t get_path(const char *src_path , uint8_t *res );
extern mp_obj_t file_type(const char *fileName);
extern mp_obj_t get_sscan(const char *sour, const char *start,const char *end,uint8_t *ret);
extern uint16_t rgb888to565(uint8_t r_color, uint8_t g_color , uint8_t b_color);
extern char* itoa(int num,char* str,int radix);
extern int atoi(const char *nptr);
extern bool check_sys_file(const char *check_file);
extern ssize_t jpg_save(const char *filename, uint8_t *wbuf, ssize_t len);

#ifdef __cplusplus
}
#endif

#endif // __GLOBAL_H