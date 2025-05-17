import adafruit_connection_manager
import adafruit_requests
import audiobusio
import audiomp3
import board
import digitalio
import gc
import select
import time
import wifi
from os import getenv

import board
import busio
import displayio
import adafruit_displayio_ssd1306
import adafruit_displayio_sh1106
from adafruit_display_text import label
import terminalio
import adafruit_imageload
import os
from adafruit_progressbar.progressbar import HorizontalProgressBar

# Setup the display
displayio.release_displays()
# Initialize I2C on GP0 (SDA), GP1 (SCL)
i2c = busio.I2C(scl=board.GP15, sda=board.GP14)

# Wait for I2C to be ready
while not i2c.try_lock():
    pass
print("I2C addresses:", [hex(device) for device in i2c.scan()])
i2c.unlock()

# Setup the display
displayio.release_displays()


from i2cdisplaybus import I2CDisplayBus

display_bus = I2CDisplayBus(i2c, device_address=0x3C)

# display_bus = displayio.I2CDisplay(i2c, device_address=0x3C)
display = adafruit_displayio_sh1106.SH1106(display_bus, width=130, height=64)

# set progress bar width and height relative to board's display
BAR_WIDTH =  57
BAR_HEIGHT = 10
x = 71
y = 50



# Create a display group
splash = displayio.Group()
text = label.Label(terminalio.FONT, text="Podcast Radio", x=15, y=30)
splash.append(text)
#text = label.Label(terminalio.FONT, text="* Drinnies", x=15, y=20)
#splash.append(text)
#text = label.Label(terminalio.FONT, text="* Podcast UFO", x=15, y=40)
#splash.append(text)
display.root_group = splash

# --- Setup b_confirm on GPIO18 ---
b_cycle = digitalio.DigitalInOut(board.GP18)
b_cycle.direction = digitalio.Direction.INPUT
b_cycle.pull = digitalio.Pull.UP  # assumes b_confirm connects to GND when pressed

# --- Button ---
b_confirm = digitalio.DigitalInOut(board.GP17)
b_confirm.direction = digitalio.Direction.INPUT
b_confirm.pull = digitalio.Pull.UP
last_b_confirm_state = b_confirm.value
# --- Button ---
b_menu = digitalio.DigitalInOut(board.GP19)
b_menu.direction = digitalio.Direction.INPUT
b_menu.pull = digitalio.Pull.UP

rss_map = {
    "/sd/ufo.bmp": "https://feeds.acast.com/public/shows/0301869f-de1f-4fac-97f9-ed5bf6faab23",
    "/sd/drinnies.bmp": "https://feeds.acast.com/public/shows/686e98a6-24b8-4ca4-98bb-16ef4ade7aed"
}

def show_image(path,state):
    
    # Create a new progress_bar object at (x, y)
    progress_bar = HorizontalProgressBar(
        (x, y),
        (BAR_WIDTH, BAR_HEIGHT),
        bar_color=0xFFFFFF,
        outline_color=0xAAAAAA,
        fill_color=0x777777,
    )

    # load image
    image, palette = adafruit_imageload.load(
        path, bitmap=displayio.Bitmap, palette=displayio.Palette
    )
    tile_grid = displayio.TileGrid(image, pixel_shader=palette)
    text = label.Label(terminalio.FONT, text=state, x=80, y=30)
    group = displayio.Group()
    group.append(tile_grid)
    group.append(text)
    group.append(progress_bar)
    return group
    
def estimate_duration(file_size_bytes, bitrate_kbps=128):
    return (file_size_bytes * 8) / (bitrate_kbps * 1000)
    
## --- List BMP images in /sd ---
#image_paths = [
#    "/sd/" + f for f in os.listdir("/sd")
#    if f.lower().endswith(".bmp") and not f.startswith("._")]
#image_paths.sort()  # optional: alphabetical order
#print("Found images:", image_paths)

# --- Show first image ---
#current_index = 0
#display.root_group = show_image(image_paths[current_index])

# --- Main loop: cycle images on b_confirm press ---
#last_state = b_cycle.value
#last_confirm_state = b_confirm.value



def menu():
        # --- List BMP images in /sd ---
    image_paths = [
        "/sd/" + f for f in os.listdir("/sd")
        if f.lower().endswith(".bmp") and not f.startswith("._")]
    image_paths.sort()  # optional: alphabetical order
    print("Found images:", image_paths)

    # --- Show first image ---
    current_index = 0
    display.root_group = show_image(image_paths[current_index],"Menu")

    # --- Main loop: cycle images on b_confirm press ---
    last_state = b_cycle.value
    last_confirm_state = b_confirm.value
    while True:
        current_state = b_cycle.value
        if not current_state and last_state:  # b_confirm just pressed
            current_index = (current_index + 1) % len(image_paths)
            print("Showing:", image_paths[current_index])
            display.root_group = show_image(image_paths[current_index],"Menu")
        last_state = current_state
        time.sleep(0.05)  # debounce
        
        # Confirm b_confirm
        current_confirm_state = b_confirm.value
        if not current_confirm_state and last_confirm_state:
            # Get basename of current image
            img_name = image_paths[current_index]
            rss_url = rss_map.get(img_name, None)
            if rss_url:
                print("Confirmed RSS URL:", rss_url)
                display.root_group = show_image(image_paths[current_index],"Download")

                return rss_url
            else:
                print("No RSS URL mapped for", img_name)
            time.sleep(0.05)  # simple debounce

        last_confirm_state = current_confirm_state

# --- Helpers ---
def show_mp3_props(decoder):
    print("Sample Rate:", decoder.sample_rate, "Hz")
    print("Bits per Sample:", decoder.bits_per_sample)
    print("Channels:", decoder.channel_count)
    print(
        "Data Rate:",
        (decoder.sample_rate * decoder.bits_per_sample * decoder.channel_count) / 1000,
        "kbits/s",
    )


def show_mem():
    gc.collect()
    print("Free memory:", gc.mem_free())


def socket_readable(sock):
    global poll
    if poll is None:
        poll = select.poll()
    poll.register(sock, select.POLLIN)
    events = poll.poll(0)
    for s, event in events:
        if s == sock and (event & select.POLLIN):
            return True
    return False


# --- Wi-Fi ---
ssid = getenv("CIRCUITPY_WIFI_SSID")
password = getenv("CIRCUITPY_WIFI_PASSWORD")

print(f"Connecting to {ssid}...")
wifi.radio.connect(ssid, password)
print("Wifi Connected!")


# --- Audio ---
i2s = audiobusio.I2SOut(board.GP0, board.GP1, board.GP2)
mp3_buffer = bytearray(16384)
mp3_decoder = None

# --- HTTP session ---
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
requests = adafruit_requests.Session(pool, ssl_context)


# XML_URL = "https://feeds.acast.com/public/shows/686e98a6-24b8-4ca4-98bb-16ef4ade7aed" # drinnies
#XML_URL = "https://feeds.acast.com/public/shows/0301869f-de1f-4fac-97f9-ed5bf6faab23"  # podcast ufo
# Make a streaming GET request
rss_feed = menu()

def get_streaming_url(rss_feed):
    response = requests.get(rss_feed, stream=True)

    chunk_size = 1024  # bytes per chunk
    print("Reading XML in chunks:")
    STREAMING_URL = ""

    for chunk in response.iter_content(chunk_size):
        d_chunk = chunk.decode("utf-8")
        if "<enclosure url=" and ".mp3" in d_chunk:
            start = d_chunk.find('<enclosure url="')
            if start != -1:
                start += len('<enclosure url="')
                end = d_chunk.find('"', start)
                url = d_chunk[start:end]
                print(f"found url: {url}")
                response.close()
                return url
            else:
                print("No enclosure tag found.")

def get_streaming_url_with_length(rss_feed):
    response = requests.get(rss_feed, stream=True)

    chunk_size = 1024  # bytes per chunk
    print("Reading XML in chunks:")
    STREAMING_URL = ""
    for chunk in response.iter_content(chunk_size):
        d_chunk = chunk.decode("utf-8")
        if "<enclosure url=" in d_chunk and ".mp3" in d_chunk:
            start = d_chunk.find('<enclosure url="')
            if start != -1:
                start += len('<enclosure url="')
                end = d_chunk.find('"', start)
                url = d_chunk[start:end]

                # Find length="..."
                length_start = d_chunk.find('length="', end)
                if length_start != -1:
                    length_start += len('length="')
                    length_end = d_chunk.find('"', length_start)
                    length = int(d_chunk[length_start:length_end])
                else:
                    length = None  # fallback

                print(f"found url: {url}")
                print(f"length: {length} bytes")
                response.close()
                return url, length


STREAMING_URL,MP3_LENGTH = get_streaming_url_with_length(rss_feed)
# --- Polling setup ---
poll = None






# --- Playing Loop ---
while True:
    print("\n Playing loop now!")
    # for every time we get out of the menu things have to be reset here.
    # Add a flag to track pause state
    paused = False

    try:
        with requests.get(
            STREAMING_URL, headers={"connection": "close"}, stream=True
        ) as response:
            label_layer = display.root_group[1] # assuming it's still the second element
            progress_bar = display.root_group[2]
            
            
            if mp3_decoder is None:
                mp3_decoder = audiomp3.MP3Decoder(response.socket, mp3_buffer)
            else:
                mp3_decoder.file = response.socket

            if socket_readable(response.socket):
                print("playback...")
                label_layer.text = "Playing"
                progress_bar.value = 0
                i2s.play(mp3_decoder)



                while i2s.playing:
                    current_b_confirm = b_confirm.value
                    if current_b_confirm != last_b_confirm_state and not current_b_confirm:
                        if not paused:
                            print("\nPausing playback.")
                            label_layer.text = "Paused"
                            i2s.pause()
                            paused = True
                        else:
                            print("\nResuming playback.")
                            label_layer.text = "Playing"
                            i2s.resume()
                            paused = False
                    last_b_confirm_state = current_b_confirm
                    time.sleep(0.05)
                    #progress_bar.value += 1/128
                    # refresh the display
                    #display.refresh()
                    
                    current_state = b_menu.value
                    if not current_state and last_state:  # b_confirm just pressed
                        i2s.stop()
                        rss_feed = menu()
                        STREAMING_URL,MP3_LENGTH = get_streaming_url_with_length(rss_feed)
                        break
                    last_state = current_state
                    time.sleep(0.05)  # debounce

            if poll:
                poll.unregister(response.socket)
            if response.socket:
                response.socket.close()

    except Exception as e:
        print("Error during playback:", e)

print("Done.")
