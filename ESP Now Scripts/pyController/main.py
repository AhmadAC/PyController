# pyController\main.py
import network
import espnow
import time
import struct
import controller
import tftlcd

# 1. Setup LCD
l = tftlcd.LCD15()
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GREEN = (0, 150, 0)
RED = (255, 0, 0)

# Clear to white first to indicate boot
l.fill(WHITE)
l.printStr("Booting...", 10, 10, color=BLACK, backcolor=WHITE, size=2)

# 2. Setup ESP-NOW
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
try:
    wlan.disconnect()
except Exception:
    pass
wlan.config(channel=1)

esp = espnow.ESPNow()
esp.active(True)

BROADCAST = b'\xff\xff\xff\xff\xff\xff'
try:
    esp.add_peer(BROADCAST)
except OSError:
    pass

PEER_MAC = None
gamepad = controller.CONTROLLER()

# --- Pairing Logic ---
l.fill(WHITE)
l.printStr("Searching for pyCar...", 10, 100, color=BLACK, backcolor=WHITE, size=2)
print("Searching for pyCar...")

while PEER_MAC is None:
    try:
        esp.send(BROADCAST, b'pyCAR_DISCOVER')
    except OSError:
        pass
    
    # Wait for up to 250ms, yielding with sleep_ms(10) to prevent 
    # Native USB/TinyUSB stack from freezing and IDE auto-disconnecting.
    wait_start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), wait_start) < 250:
        try:
            host, msg = esp.recv(0) # Non-blocking read
            if msg == b'pyCAR_ACK':
                PEER_MAC = host
                try:
                    esp.add_peer(PEER_MAC)
                except OSError:
                    pass
                print("Connected to Car:", PEER_MAC)
                break
        except Exception:
            pass
            
        time.sleep_ms(10) # Important: Feeds the USB stack!

# --- Initial UI Render ---
l.fill(WHITE)
try:
    l.Picture(0, 0, 'picture/Car.jpg')
except Exception:
    pass
    
l.printStr("Connected!", 10, 10, color=GREEN, backcolor=WHITE, size=2)
l.printStr("Ultrasonic:", 10, 160, color=BLACK, backcolor=WHITE, size=2)

# --- Timers and State Variables ---
last_tx_time = time.ticks_ms()
last_lcd_update_time = time.ticks_ms() 
last_print_time = time.ticks_ms()

last_dist_str_on_screen = ""      
latest_received_dist_str = "" 

last_line_follower_state = False
latest_line_follower_state = False

last_sync_state = False
latest_sync_state = False

print("--- Starting Main Loop ---")

# --- Main Control Loop ---
while True:
    now = time.ticks_ms()
    
    # 1. NON-BLOCKING: Drain the entire RX queue as fast as possible.
    while True:
        try:
            host, msg = esp.recv(0)
            if not msg:
                break 
                
            if msg.startswith(b'D:'):
                decoded_msg = msg.decode('utf-8')
                parts = decoded_msg.split(',')
                for p in parts:
                    if p.startswith('D:'):
                        latest_received_dist_str = p[2:]
                    elif p.startswith('L:'):
                        latest_line_follower_state = (p[2:] == '1')
                    elif p.startswith('X:'):
                        latest_sync_state = (p[2:] == '1')
        except Exception:
            break

    # 2. RATE-LIMITED LCD UPDATE (NO ANIMATION/ROLLING FIX)
    if time.ticks_diff(now, last_lcd_update_time) >= 200:
        # Distance text update
        if latest_received_dist_str and latest_received_dist_str != last_dist_str_on_screen:
            # Format text and pad with spaces (<12) to flawlessly overwrite the old characters
            display_text = f"{latest_received_dist_str} cm"
            padded_text = f"{display_text:<12}" 
            
            l.printStr(padded_text, 10, 190, color=BLACK, backcolor=WHITE, size=2)
            last_dist_str_on_screen = latest_received_dist_str
        
        # Line Follower Icon (Black) Update
        if latest_line_follower_state != last_line_follower_state:
            try:
                if latest_line_follower_state:
                    l.drawCircle(220, 20, 10, BLACK, fillcolor=BLACK)
                else:
                    l.drawCircle(220, 20, 10, WHITE, fillcolor=WHITE)
            except AttributeError:
                if latest_line_follower_state:
                    l.drawRect(210, 10, 20, 20, BLACK, border=1, fillcolor=BLACK)
                else:
                    l.drawRect(210, 10, 20, 20, WHITE, border=1, fillcolor=WHITE)
            last_line_follower_state = latest_line_follower_state

        # Sync Mode Icon (Red) Update
        if latest_sync_state != last_sync_state:
            try:
                if latest_sync_state:
                    l.drawCircle(190, 20, 10, RED, fillcolor=RED)
                else:
                    l.drawCircle(190, 20, 10, WHITE, fillcolor=WHITE)
            except AttributeError:
                if latest_sync_state:
                    l.drawRect(180, 10, 20, 20, RED, border=1, fillcolor=RED)
                else:
                    l.drawRect(180, 10, 20, 20, WHITE, border=1, fillcolor=WHITE)
            last_sync_state = latest_sync_state

        last_lcd_update_time = now # Reset the LCD timer

    # 3. Rate-limited joystick data transmission
    if time.ticks_diff(now, last_tx_time) >= 50: # ~20Hz
        try:
            key = gamepad.read()
            payload = struct.pack('<BBBBBB', 67, key[1], key[2], key[3], key[4], key[5])
            esp.send(PEER_MAC, payload)
            
            # Safe diagnostic printing
            if time.ticks_diff(now, last_print_time) >= 500:
                print(f"TX Joy: L({key[1]},{key[2]}) R({key[3]},{key[4]}) BTN: {key[5]:08b}")
                last_print_time = now
                
        except Exception:
            pass # Ignore occasional send errors
            
        last_tx_time = now

    time.sleep_ms(5)