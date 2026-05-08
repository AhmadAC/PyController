# usermod/micropython.cmake

add_library(usermod_pycontroller INTERFACE)

# Add all your .c files here (LCD + Controller)
target_sources(usermod_pycontroller INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/global.c
    ${CMAKE_CURRENT_LIST_DIR}/lcd_spibus.c
    ${CMAKE_CURRENT_LIST_DIR}/modtftlcd.c
    ${CMAKE_CURRENT_LIST_DIR}/ILI9341.c
    ${CMAKE_CURRENT_LIST_DIR}/ST7735.c
    ${CMAKE_CURRENT_LIST_DIR}/ST7789.c
    ${CMAKE_CURRENT_LIST_DIR}/piclib.c
    ${CMAKE_CURRENT_LIST_DIR}/bmp.c
    ${CMAKE_CURRENT_LIST_DIR}/tjpgd.c
    ${CMAKE_CURRENT_LIST_DIR}/modcontroller.c
    ${CMAKE_CURRENT_LIST_DIR}/modgamepad.c
    ${CMAKE_CURRENT_LIST_DIR}/psxcontroller.c
)

# Tell the compiler where to find the .h files
target_include_directories(usermod_pycontroller INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}
)

# Link your custom module to the main MicroPython build
target_link_libraries(usermod INTERFACE usermod_pycontroller)