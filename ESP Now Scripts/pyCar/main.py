# pyCar\main.py
import network
import espnow
import time
import struct
import car as car_module # Imported to access the global count1 and count2 encoder variables
from car import CAR

# 1. Setup Wi-Fi and ESP-NOW
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
try:
    wlan.disconnect() # Prevent connection to AP which changes the channel
except Exception:
    pass
wlan.config(channel=1)

esp = espnow.ESPNow()
esp.active(True)

# Add broadcast address so we can hear discovery pings
BROADCAST = b'\xff\xff\xff\xff\xff\xff'
try:
    esp.add_peer(BROADCAST)
except OSError:
    pass

Car = CAR()
Car.oled.fill(0)
Car.oled.text("ESP-NOW Pairing...", 0, 0)
Car.oled.show()

PEER_MAC = None

# State variables
headlight_state = False
last_light_btn = False

line_follower_state = False
last_a_btn = False

current_distance = 999.0 # Start with a safe distance

# Line Follower Memory
last_line_pos = 0.0 # Memory tracker for the 1cm line's last known location
last_error = 0.0    # Used for the PD controller to predict line movement

# Dynamic Encoder Calibration variables
target_m1 = 0
target_m2 = 0
m1_pwm_trim = 1.0 # Multiplier for left motor speed
m2_pwm_trim = 1.0 # Multiplier for right motor speed
last_count1 = 0
last_count2 = 0
last_encoder_time = time.ticks_ms()

def safe_get_distance():
    # Bypass the buggy Car.getDistance() to avoid freezing if the sensor fails
    Car.trig.value(1)
    time.sleep_us(20)
    Car.trig.value(0)
    
    t0 = time.ticks_us()
    while Car.echo.value() == 0:
        if time.ticks_diff(time.ticks_us(), t0) > 30000: # 30ms timeout (Sensor Error)
            return -1.0
            
    t1 = time.ticks_us()
    while Car.echo.value() == 1:
        if time.ticks_diff(time.ticks_us(), t1) > 30000:
            return -1.0
            
    t2 = time.ticks_us()
    return ((t2 - t1) * 170) / 10000

# --- Pairing Logic ---
print("Waiting for Controller...")
while PEER_MAC is None:
    try:
        # Use non-blocking recv with a yield loop so Native USB doesn't freeze
        wait_start = time.ticks_ms()
        while time.ticks_diff(time.ticks_ms(), wait_start) < 500:
            try:
                host, msg = esp.recv(0)
                if msg == b'pyCAR_DISCOVER':
                    PEER_MAC = host
                    try:
                        esp.add_peer(PEER_MAC)
                    except OSError:
                        pass
                        
                    try:
                        esp.send(PEER_MAC, b'pyCAR_ACK') # Tell controller we found it
                        print("Paired with:", PEER_MAC)
                    except OSError as e:
                        print("Error sending ACK:", e)
                        PEER_MAC = None # Retry
                    break
            except Exception:
                pass
                
            time.sleep_ms(10) # Feeds background tasks
    except KeyboardInterrupt:
        pass
    except Exception:
        pass

Car.oled.fill(0)
Car.oled.text("Paired!", 0, 0)
Car.oled.show()
time.sleep(1)

# Ensure the OLED red LED status icon is turned off permanently
Car.s_red = 0
Car.screen()

last_dist_time = time.ticks_ms()
last_print_time = time.ticks_ms()
print("--- Starting Main Loop ---")

# --- Main Control Loop ---
while True:
    try:
        latest_joy_msg = None
        
        # Drain the queue to ensure zero input latency
        while True:
            try:
                host, msg = esp.recv(0)
                if not msg:
                    break
                    
                if msg == b'pyCAR_DISCOVER':
                    try:
                        esp.send(host, b'pyCAR_ACK')
                    except OSError:
                        pass
                elif len(msg) == 6 and msg[0] == 67: 
                    latest_joy_msg = msg # Overwrite with the newest packet
            except Exception:
                break

        now = time.ticks_ms()

        # --- Encoder Speed Calibration (Auto-Trim) ---
        if time.ticks_diff(now, last_encoder_time) > 100:
            current_count1 = car_module.count1
            current_count2 = car_module.count2
            
            spd1 = current_count1 - last_count1
            spd2 = current_count2 - last_count2
            
            last_count1 = current_count1
            last_count2 = current_count2
            last_encoder_time = now
            
            # Only trim when the target speeds for both sides are identical (driving straight)
            if abs(target_m1) > 200 and target_m1 == target_m2:
                if spd1 > spd2 + 1:
                    m1_pwm_trim -= 0.02 # Left side is faster, slow it down
                elif spd2 > spd1 + 1:
                    m2_pwm_trim -= 0.02 # Right side is faster, slow it down
                elif spd1 == spd2:
                    # If speeds are equal, slowly return trims to 1.0
                    if m1_pwm_trim < 1.0: m1_pwm_trim += 0.01
                    if m2_pwm_trim < 1.0: m2_pwm_trim += 0.01
                    
                m1_pwm_trim = max(0.5, min(1.0, m1_pwm_trim))
                m2_pwm_trim = max(0.5, min(1.0, m2_pwm_trim))
            else:
                # If not driving straight, gradually reset trims
                if m1_pwm_trim < 1.0: m1_pwm_trim += 0.05
                if m2_pwm_trim < 1.0: m2_pwm_trim += 0.05
                m1_pwm_trim = min(1.0, m1_pwm_trim)
                m2_pwm_trim = min(1.0, m2_pwm_trim)

        # Process only the most recent joystick packet
        if latest_joy_msg:
            _, lx, ly, rx, ry, btns = struct.unpack('<BBBBBB', latest_joy_msg)
            
            # Initialize motor speeds to zero
            m1, m2, m3, m4 = 0, 0, 0, 0
            target_m1, target_m2 = 0, 0

            # B Button Toggles Headlights
            light_pressed = (btns & 0x20) != 0
            if light_pressed and not last_light_btn:
                headlight_state = not headlight_state
                Car.light(1 if headlight_state else 0)
                print("TOGGLED HEADLIGHT:", "ON" if headlight_state else "OFF")
            last_light_btn = light_pressed

            # A Button Toggles Line Follower
            a_pressed = (btns & 0x10) != 0
            if a_pressed and not last_a_btn:
                line_follower_state = not line_follower_state
                print("TOGGLED LINE FOLLOWER:", "ON" if line_follower_state else "OFF")
            last_a_btn = a_pressed
            
            # --- Industry Standard Arcade Drive Logic ---
            turn_input = lx - 128
            left_drive_input = ly - 128
            right_drive_input = ry - 128 
            
            # Use whichever joystick is being pushed further forward/backward
            if abs(left_drive_input) > abs(right_drive_input):
                drive_input = left_drive_input
            else:
                drive_input = right_drive_input
            
            # Deadband to ignore slight joystick drift when sticks sit near the center
            if abs(turn_input) <= 15:
                turn_input = 0
            if abs(drive_input) <= 15:
                drive_input = 0
                
            throttle = int(drive_input * 1023 / 128)
            steering = int(turn_input * 1023 / 128)
            
            # --- FIXED: Intuitive Reversing ---
            # If we are reversing (throttle < 0), invert the steering direction 
            # so the back of the car swings in the direction you push the stick
            if throttle < 0:
                steering = -steering
            
            # Differential / Arcade Drive Mixing
            left_speed = throttle + steering
            right_speed = throttle - steering
            
            # Clamp limits to standard motor values to prevent overflow
            left_speed = max(-1023, min(1023, left_speed))
            right_speed = max(-1023, min(1023, right_speed))
            
            # Apply to wheels (Left side = M1/M4, Right side = M2/M3)
            m1 = left_speed
            m4 = -left_speed  # M4 is inverted for forward
            m2 = right_speed
            m3 = right_speed
            
            # Update targets for dynamic encoder calibration (auto-trim will only run when driving straight)
            target_m1 = left_speed
            target_m2 = right_speed

            # --- D-Pad Overrides ---
            dpad = btns & 0x0F
            if dpad == 0: # D-Pad Up
                m1, m2, m3, m4 = 1023, 1023, 1023, -1023
            elif dpad == 4: # D-Pad Down
                m1, m2, m3, m4 = -1023, -1023, -1023, 1023

            # --- Centering Line Follower Logic (PD Controller + Memory) ---
            # Manually overriding standard operation if ANY stick is moved
            manual_override = (abs(lx - 128) > 15 or abs(ly - 128) > 15 or abs(ry - 128) > 15 or dpad != 8)
            
            if line_follower_state and not manual_override:
                # Invert the values. The sensors return 0 for the Black Line, 1 for White Floor.
                v1 = 1 - Car.t1.value() # Far left
                v2 = 1 - Car.t2.value() # Left
                v3 = 1 - Car.t3.value() # Center
                v4 = 1 - Car.t4.value() # Right
                v5 = 1 - Car.t5.value() # Far right
                
                active_sensors = v1 + v2 + v3 + v4 + v5
                
                if active_sensors > 0:
                    # Calculate a weighted average (-2.0 to 2.0).
                    pos = (-2.0*v1 + -1.0*v2 + 0.0*v3 + 1.0*v4 + 2.0*v5) / active_sensors
                    
                    # Proportional-Derivative (PD) Control Math
                    error = pos
                    P = error * 350                  
                    D = (error - last_error) * 250   
                    
                    last_error = error               
                    last_line_pos = pos              
                    
                    steering = P + D
                    
                    # Dynamically reduce forward base speed the further off-center we are.
                    base_speed = 500 - (abs(error) * 150) 
                    
                    left_speed = int(base_speed + steering)
                    right_speed = int(base_speed - steering)
                else:
                    # Sensor blind spot / memory hunting
                    if last_line_pos < -0.2:
                        left_speed = -450   # Spin Left
                        right_speed = 450
                    elif last_line_pos > 0.2:
                        left_speed = 450    # Spin Right
                        right_speed = -450
                    else:
                        left_speed = 0      # Lost entirely, safely halt
                        right_speed = 0
                        
                # Clamp and mirror to all 4 wheels
                m1 = max(-1023, min(1023, left_speed))
                m4 = -m1 # Inverted!
                m2 = max(-1023, min(1023, right_speed))
                m3 = m2 

            # --- Collision Avoidance Override ---
            if current_distance <= 20.0:
                # Stop any forward motion
                if m1 > 0: m1 = 0
                if m2 > 0: m2 = 0
                if m3 > 0: m3 = 0
                if m4 < 0: m4 = 0 # m4 goes forward when negative!

            # --- Apply Dynamic Trim for Synchronization ---
            # M1/M4 are on the left side, M2/M3 are on the right side
            m1 = int(m1 * m1_pwm_trim)
            m4 = int(m4 * m1_pwm_trim)
            m2 = int(m2 * m2_pwm_trim)
            m3 = int(m3 * m2_pwm_trim)

            Car.set_motors(m1, m2, m3, m4)

            # Safe diagnostic print
            if time.ticks_diff(now, last_print_time) > 500:
                if m1 != 0 or m2 != 0 or m3 != 0 or m4 != 0:
                    print(f"MOTORS: L={m1}/{m4} R={m2}/{m3} | TRIMS: {m1_pwm_trim:.2f}/{m2_pwm_trim:.2f}")
                last_print_time = now

        # Periodic Tasks (Ultrasonic & LCD refresh)
        if time.ticks_diff(now, last_dist_time) > 200:
            dist = safe_get_distance()
            if dist >= 0:
                Car.s_sr = dist
                current_distance = dist
            else:
                current_distance = 999.0 
                
            try:
                if PEER_MAC:
                    # Transmit sensor distance and line follower state
                    msg_str = f"D:{dist:.2f},L:{1 if line_follower_state else 0},X:0" # X:0 as sync is removed
                    esp.send(PEER_MAC, msg_str.encode())
            except OSError:
                pass
                
            Car.screen() 
            last_dist_time = time.ticks_ms()
            
        time.sleep_ms(5)
        
    except KeyboardInterrupt:
        pass