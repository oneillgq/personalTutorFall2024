from adafruit_display_text import label, scrolling_label
from adafruit_displayio_layout.layouts.grid_layout import GridLayout
import terminalio
import time
from micropython import const
from adafruit_seesaw.seesaw import Seesaw
from adafruit_progressbar.horizontalprogressbar import HorizontalProgressBar, HorizontalFillDirection
import os
import sys
import ssl
import wifi
import socketpool
import adafruit_requests
import adafruit_imageload
from io import BytesIO
import displayio
import adafruit_hx8357
import adafruit_tsc2007
import board


# release anything previously on screen
displayio.release_displays()

# gamepad setup
BUTTON_X = const(6)
BUTTON_Y = const(2)
BUTTON_A = const(5)
BUTTON_B = const(1)
BUTTON_SELECT = const(0)
BUTTON_START = const(16)
button_mask = const(
    (1 << BUTTON_X)
    | (1 << BUTTON_Y)
    | (1 << BUTTON_A)
    | (1 << BUTTON_B)
    | (1 << BUTTON_SELECT)
    | (1 << BUTTON_START)
)

i2c_bus = board.STEMMA_I2C()

seesaw = Seesaw(i2c_bus, addr=0x50)
seesaw.pin_mode_bulk(button_mask, seesaw.INPUT_PULLUP)

# screen setup
spi = board.SPI()

tft_cs = board.IO1
tft_dc = board.IO3

display_width = 320
display_height = 480

display_bus = displayio.FourWire(spi, command=tft_dc, chip_select=tft_cs)
display = adafruit_hx8357.HX8357(display_bus, width=display_width, height=display_height, rotation=270)

i2c = board.I2C()

irq_dio = None
tsc = adafruit_tsc2007.TSC2007(i2c, irq=irq_dio)

# init start screen
start_screen_elements = displayio.Group()
start_title = label.Label(terminalio.FONT, scale = 3, x = 11, y = 25, text = f"{'Welcome to':^16}\n{'Personal Tutor':^16}")
start_screen_elements.append(start_title)

start_img = displayio.OnDiskBitmap("/start_image.bmp")
start_img = displayio.TileGrid(start_img, pixel_shader = start_img.pixel_shader, y = 100)
start_screen_elements.append(start_img)

#50 chars per line max
subtext = """Push SELECT to enter search screen. Use stick to
move, A to enter, B to delete, X for space, SELECT
to search, or Y to move to results. In results,
Use A to load card or START to return to keyboard.
In card, touch to draw, change color/erase w/D-pad.
Clear w/START & exit w/SELECT. Have fun!
"""

start_subtext = label.Label(terminalio.FONT, scale = 1, x = 11, y = 380, text = subtext)
start_screen_elements.append(start_subtext)

#wifi setup + URL
try:
    print("Connecting to WiFi...")
    wifi.radio.connect(os.getenv("WIFI_SSID"), os.getenv("WIFI_PASSWORD"))
    print("Connected!")
except OSError:
    print("Failed to Connect to WiFi.")
    print("Update settings.toml or try again!")
    sys.exit()

pool = socketpool.SocketPool(wifi.radio)
requests = adafruit_requests.Session(pool, ssl.create_default_context())

URL = "https://api.magicthegathering.io/v1/cards?contains=imageUrl"

# init search screen
search_screen_elements = displayio.Group()

KEYBOARD_COLOR = 0x0000FF
BORDER_COLOR = 0xFFFFFF
TEXT_COLOR = 0xFFFFFF
KEYBOARD_HIGHLIGHT = 0xFF0000
RESULT_HIGHLIGHT = 0x03fc8c

keyboard = GridLayout(
    x = 33, y = 342,
    width = 254, height = 128,
    grid_size = (7, 4),
    divider_lines = True, divider_line_color = BORDER_COLOR
)

i = 0
chars = "abcdefghijklmnopqrstuvwxyz-'"

for y_temp in range(4):
    for x_temp in range(7):
        l = label.Label(terminalio.FONT, scale = 2, padding_bottom = 3, text = f" {chars[i]} ", background_color = KEYBOARD_COLOR)
        keyboard.add_content(l, grid_position = (x_temp, y_temp), cell_size = (1, 1))
        i += 1

search_bar = GridLayout(
    x = 16, y = 10,
    width = 288, height = 32,
    grid_size = (1, 1), cell_padding = 5,
    divider_lines = True, divider_line_color = BORDER_COLOR
)

search_results = GridLayout(
    x = 16, y = 52,
    width = 288, height = 288,
    grid_size = (1,9)
)

for y_temp in range(8):
    l = scrolling_label.ScrollingLabel(terminalio.FONT, scale = 2, x = 0, y = 0,text = "", max_characters = 23, animate_time = 1)
    search_results.add_content(l, grid_position = (0,y_temp), cell_size = (1,1))

search_bar_content = label.Label(terminalio.FONT, scale = 2, x = 0, y = 0, text = "")
search_bar.add_content(search_bar_content, grid_position = (0,0), cell_size = (1,1))

search_screen_elements.append(search_bar)
search_screen_elements.append(search_results)
search_screen_elements.append(keyboard)

#global vars for caching
search_bar_text = ""
cleaned_cards = []

# progress bar init
progress_bar = HorizontalProgressBar(
    position = (20, 150), direction=HorizontalFillDirection.LEFT_TO_RIGHT,
    size = (280, 60)
)

progress_label = label.Label(terminalio.FONT, scale = 2, x = 30, y = 230, text = "", background_color=0x000000, color = 0x00FF00)

progess_label_back  = displayio.Bitmap(1, 1, 1)
progess_label_back_color = displayio.Palette(1)
progess_label_back_color[0] = 0x000000
progess_label_back = displayio.TileGrid(progess_label_back, pixel_shader = progess_label_back_color, x=0, y=150, width=320, height=90)

# functions!
def start_screen():
    display.root_group = start_screen_elements
    while True:
        buttons = seesaw.digital_read_bulk(button_mask)
        if not buttons & (1 << BUTTON_SELECT):
            return

def display_progress():
    display.root_group.append(progess_label_back)
    display.root_group.append(progress_bar)
    display.root_group.append(progress_label)

def delete_progress():
    display.root_group.pop()
    display.root_group.pop()
    display.root_group.pop()
    progress_label.text = ""
    progress_bar.value = progress_bar.minimum

def set_progress(text="", percent=0):
    if text != "":
        progress_label.text = f"{text:^22}"
    progress_bar.value = percent

def get_stick_readings():
    x = 1023 - seesaw.analog_read(14)
    y = 1023 - seesaw.analog_read(15)
    return x, y

def wait_stick(x, y):
    while abs(x - 500) > 200 or abs(y - 500) > 200:
        # update sensor vals
        x = 1023 - seesaw.analog_read(14)
        y = 1023 - seesaw.analog_read(15)

def wait_button_release(button):
    buttons = seesaw.digital_read_bulk(button_mask)
    while not buttons & (1 << button):
        buttons = seesaw.digital_read_bulk(button_mask)

def load_results(query):
    display_progress()
    set_progress("Accessing URL", 5)
    try:
        resp = requests.get(URL + f"&name={query}")
    except:
        progress_label.color = 0xFF0000
        set_progress("Failed! Try Again")
        time.sleep(2)
        progress_label.color = 0x00FF00
        return []
    set_progress("Response! Making JSON", 20)
    resp_json = resp.json()
    cards = resp_json["cards"]
    names = set()
    cleaned_cards = []
    indices_to_delete = []
    limit = 8
    set_progress("Success! Getting Names", 50)
    for index, card in enumerate(cards):
        if len(names) == 8:
            break
        name = card["name"]
        set_progress(percent = 50 + (len(names)+1)*5)
        if name not in names:
            names.add(name)
            cleaned_cards.append(card)
        else:
            indices_to_delete.append(index)
    set_progress("Names Got! Processing", 90)
    for index in range(len(cleaned_cards)):
        l = search_results.get_cell((0, index))
        l.text = cleaned_cards[index]["name"]
        l.color = 0x000000

    for index in range(len(cleaned_cards), 8):
        l = search_results.get_cell((0, index))
        l.text = ""
    set_progress(percent = 100)
    time.sleep(0.3)
    for index in range(len(cleaned_cards)):
        l = search_results.get_cell((0, index))
        l.color = 0xFFFFFF
    delete_progress()
    return cleaned_cards

def search_screen():
    display.root_group = search_screen_elements

    # search vars
    l_key_x = 0
    l_key_y = 0
    key_x = 0
    key_y = 0
    global search_bar_text
    global cleaned_cards

    for index in range(len(cleaned_cards)):
        l = search_results.get_cell((0, index))
        l.text = cleaned_cards[index]["name"]
        l.color = 0x000000

    for index in range(len(cleaned_cards), 8):
        l = search_results.get_cell((0, index))
        l.text = ""

    for index in range(len(cleaned_cards)):
        l = search_results.get_cell((0, index))
        l.color = 0xFFFFFF

    while True:
        # get stick + button readings
        x, y = get_stick_readings()
        buttons = seesaw.digital_read_bulk(button_mask)
        l = keyboard.get_cell((l_key_x, l_key_y))
        l.color = KEYBOARD_HIGHLIGHT

        if abs(x - 500) > 100 or abs(y - 500) > 100:
            # making relevant char change
            if x > 500 + 300:
                key_x = (key_x + 1) % 7
            if x < 500 - 300:
                key_x = (key_x - 1) % 7
            if y > 500 + 200:
                key_y = (key_y - 1) % 4
            if y < 500 - 200:
                key_y = (key_y + 1) % 4

            # un-highlight prev key
            l = keyboard.get_cell((l_key_x, l_key_y))
            l.color = TEXT_COLOR

            #highlight new key
            l = keyboard.get_cell((key_x, key_y))
            l.color = KEYBOARD_HIGHLIGHT

            #update last keys
            l_key_x = key_x
            l_key_y = key_y

            wait_stick(x, y)

        # button X adds a space
        if not buttons & (1 << BUTTON_X):
            l = keyboard.get_cell((key_x, key_y))
            search_bar_text = search_bar_text + " "
            search_bar_content.text = search_bar_text[-23:]

            wait_button_release(BUTTON_X)

        # button A adds curr char
        if not buttons & (1 << BUTTON_A):
            l = keyboard.get_cell((key_x, key_y))
            search_bar_text = search_bar_text + l.text[1]
            search_bar_content.text = search_bar_text[-23:]

            wait_button_release(BUTTON_A)

        # button B deletes last char
        if not buttons & (1 << BUTTON_B):
            search_bar_text = search_bar_text[:-1]
            search_bar_content.text = search_bar_text[-23:]

            wait_button_release(BUTTON_B)

        # exit search screen
        if not buttons & (1 << BUTTON_START):
            return None


        # button SEL enters search and moves to search select
        if (not buttons & (1 << BUTTON_SELECT)) or (not buttons & (1 << BUTTON_Y)):
            # un-highlighting keyboard
            l = keyboard.get_cell((l_key_x, l_key_y))
            l.color = TEXT_COLOR
            wait_button_release(BUTTON_SELECT)

            if not buttons & (1 << BUTTON_SELECT):
                cleaned_cards = load_results(search_bar_text)


            # setting starting result
            l_result_i = 0
            result_i = 0

            # highlighting first result
            l = search_results.get_cell((0, result_i))
            l.color = RESULT_HIGHLIGHT

            while True:
                # if no cards were found, just exit
                if len(cleaned_cards) == 0:
                    break

                # get stick + button readings
                x, y = get_stick_readings()
                buttons = seesaw.digital_read_bulk(button_mask)

                # update if scrolling needed for selected result
                l = search_results.get_cell((0, result_i))
                l.update()

                # if stick moved, move appropriately
                if abs(y - 500) > 100:
                    if y > 500 + 200:
                        result_i = (result_i - 1) % 8
                    if y < 500 - 200:
                        result_i = (result_i + 1) % 8

                    # un-highlight prev result, and stop scrolling
                    l = search_results.get_cell((0, l_result_i))
                    l.color = TEXT_COLOR
                    l.current_index = 0
                    l.update(True)

                    # highlight new result
                    l = search_results.get_cell((0, result_i))
                    l.color = RESULT_HIGHLIGHT
                    l_result_i = result_i

                    wait_stick(x, y)

                if not buttons & (1 << BUTTON_START):
                    l = search_results.get_cell((0, result_i))
                    l.color = TEXT_COLOR
                    wait_button_release(BUTTON_START)
                    break

                if not buttons & (1 << BUTTON_A):
                    return cleaned_cards[result_i]["imageUrl"]

def card_screen(image_link):
    display_progress()
    set_progress("Getting Image Bytes", 5)
    try:
        img = requests.get(image_link)
    except:
        progress_label.color = 0xFF0000
        set_progress("Failed! Try Again")
        time.sleep(2)
        progress_label.color = 0x00FF00
        return
    img_bytes = BytesIO(img.content)

    set_progress("Got Image! Processing", 20)
    try:
        image, palette = adafruit_imageload.load(img_bytes)
    except:
        progress_label.color = 0xFF0000
        set_progress("Website is Down!")
        time.sleep(2)
        sys.exit(1)
    set_progress("Processed! Resizing", 60)
    resized_image = displayio.Bitmap(320, 448, 65535)

    for y in range(resized_image.height):
        y_og = int((y / (resized_image.height - 1)) * (image.height - 1))
        for x in range(resized_image.width):
            x_og = int((x / (resized_image.width - 1)) * (image.width - 1))
            resized_image[x, y] = image[x_og, y_og]
        set_progress(percent = 60 + int((35 * y) / resized_image.height))

    image = resized_image

    set_progress("Resized! Displaying", 100)
    time.sleep(0.3)
    delete_progress()
    card_image = displayio.TileGrid(image, pixel_shader=palette, y=16)

    background = displayio.Bitmap(1, 1, 1)
    background_color = displayio.Palette(1)
    background_color[0] = 0xFFFFFF
    background = displayio.TileGrid(background, pixel_shader=background_color, width=320, height=480)

    canvas = displayio.Bitmap(320, 480, 4)
    canvas_color = displayio.Palette(4)
    canvas_color[1] = 0xff0000
    canvas_color[2] = 0x00ff00
    canvas_color[3] = 0x0000ff

    canvas_color.make_transparent(0)
    canvas_tile = displayio.TileGrid(canvas, pixel_shader=canvas_color)

    group = displayio.Group(scale=1)

    group.append(background)
    group.append(card_image)
    group.append(canvas_tile)

    display.root_group = group

    pixel_size = 5
    touch_color = 1

    while True:
        buttons = seesaw.digital_read_bulk(button_mask)
        if not buttons & (1 << BUTTON_START):
            return
        if not buttons & (1 << BUTTON_SELECT):
            for x in range(canvas.width):
                for y in range(canvas.height):
                    canvas[x, y] = 0
        if not buttons & (1 << BUTTON_X):
            touch_color = 1
        if not buttons & (1 << BUTTON_A):
            touch_color = 2
        if not buttons & (1 << BUTTON_B):
            touch_color = 3
        if not buttons & (1 << BUTTON_Y):
            touch_color = 0

        if tsc.touched:
            point = tsc.touch
            x = int(((point["x"] - 300) / 3400) * 310)
            y = int(((point["y"] - 250) / 3600) * 470)
            if x < 320 and y < 480:
                for i in range(pixel_size):
                    for j in range(pixel_size):
                        x_pixel = x - (pixel_size // 2) + i
                        y_pixel = y - (pixel_size // 2) + j
                        if (
                                0 <= x_pixel < 320
                                and 0 <= y_pixel < 480
                        ):
                            canvas[x_pixel, y_pixel] = touch_color

img_url = None

while True:
    if img_url == None:
        start_screen()
    img_url = search_screen()
    if img_url != None:
        card_screen(img_url)


