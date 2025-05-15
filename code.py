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


# --- Helpers ---
def show_mp3_props(decoder):
    print("Sample Rate:", decoder.sample_rate, "Hz")
    print("Bits per Sample:", decoder.bits_per_sample)
    print("Channels:", decoder.channel_count)
    print("Data Rate:", (decoder.sample_rate * decoder.bits_per_sample * decoder.channel_count) / 1000, "kbits/s")

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
print("Connected!")

# --- Button ---
button = digitalio.DigitalInOut(board.GP17)
button.direction = digitalio.Direction.INPUT
button.pull = digitalio.Pull.UP
last_button_state = button.value

# --- Audio ---
i2s = audiobusio.I2SOut(board.GP0, board.GP1, board.GP2)
mp3_buffer = bytearray(16384)
mp3_decoder = None

# --- HTTP session ---
pool = adafruit_connection_manager.get_radio_socketpool(wifi.radio)
ssl_context = adafruit_connection_manager.get_radio_ssl_context(wifi.radio)
requests = adafruit_requests.Session(pool, ssl_context)


#XML_URL = "https://feeds.acast.com/public/shows/686e98a6-24b8-4ca4-98bb-16ef4ade7aed" # drinnies
XML_URL = "https://feeds.acast.com/public/shows/0301869f-de1f-4fac-97f9-ed5bf6faab23" # podcast ufo

# Make a streaming GET request
response = requests.get(XML_URL, stream=True)

chunk_size = 1024  # bytes per chunk
print("Reading XML in chunks:")
STREAMING_URL = ""
try:
    for chunk in response.iter_content(chunk_size):
        d_chunk = chunk.decode("utf-8")
        if "<enclosure url=" and ".mp3" in d_chunk:
            start = d_chunk.find('<enclosure url="')
            if start != -1:
                start += len('<enclosure url="')
                end = d_chunk.find('"', start)
                url = d_chunk[start:end]
                print(f"found url: {url}")
                STREAMING_URL = url
                break
                
            else:
                print("No enclosure tag found.")
finally:
    response.close()
    print("Done reading.")

# --- Polling setup ---
poll = None


# Add a flag to track pause state
paused = True

# --- Reconnect Loop ---
reconnects = 10
while reconnects > 0:
    reconnects -= 1
    print("\nReconnecting... (remaining attempts:", reconnects, ")")

    try:
        with requests.get(STREAMING_URL, headers={"connection": "close"}, stream=True) as response:
            if mp3_decoder is None:
                mp3_decoder = audiomp3.MP3Decoder(response.socket, mp3_buffer)
            else:
                mp3_decoder.file = response.socket

            if socket_readable(response.socket):
                print("playback...")
                i2s.play(mp3_decoder)
                i2s.pause()

                while i2s.playing:
                    current_button = button.value
                    if current_button != last_button_state and not current_button:
                        if not paused:
                            print("\nButton pressed. Pausing playback.")
                            i2s.pause()
                            paused = True
                        else:
                            print("\nButton pressed. Resuming playback.")
                            i2s.resume()
                            paused = False
                    last_button_state = current_button
                    time.sleep(0.1)


            if poll:
                poll.unregister(response.socket)
            response.socket.close()

    except Exception as e:
        print("Error during playback:", e)

print("Done.")
