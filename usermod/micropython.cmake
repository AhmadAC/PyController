# usermod/micropython.cmake

add_library(usermod_pycontroller_lcd INTERFACE)

# Add all your .c files here
target_sources(usermod_pycontroller_lcd INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/global.c
    ${CMAKE_CURRENT_LIST_DIR}/lcd_spibus.c
    ${CMAKE_CURRENT_LIST_DIR}/modtftlcd.c
    ${CMAKE_CURRENT_LIST_DIR}/ILI9341.c
    ${CMAKE_CURRENT_LIST_DIR}/ST7735.c
    ${CMAKE_CURRENT_LIST_DIR}/ST7789.c
    ${CMAKE_CURRENT_LIST_DIR}/piclib.c
    ${CMAKE_CURRENT_LIST_DIR}/bmp.c
    ${CMAKE_CURRENT_LIST_DIR}/tjpgd.c
)

# Tell the compiler where to find the .h files
target_include_directories(usermod_pycontroller_lcd INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Enable all LCD and Picture features
target_compile_definitions(usermod_pycontroller_lcd INTERFACE
    MICROPY_ENABLE_TFTLCD=1
    MICROPY_HW_LCD32=1
    MICROPY_HW_LCD15=1
    MICROPY_HW_LCD18=1
    MICROPY_STRING_SIZE_24=1
    MICROPY_STRING_SIZE_32=1
    MICROPY_STRING_SIZE_48=1
    MICROPY_PY_PICLIB=1 
)

# Link your custom module to the main MicroPython build
target_link_libraries(usermod INTERFACE usermod_pycontroller_lcd)