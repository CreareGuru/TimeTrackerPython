import ctypes
import time
import datetime
import psutil
import getpass
import mysql.connector
import json
import csv
import os
import tkinter as tk
from tkinter import StringVar
from pynput import mouse, keyboard

# Load MySQL database credentials from config file
with open('db_config.json') as config_file:
    db_config = json.load(config_file)

# File path for the CSV
csv_file_path = 'timetracker_log.csv'

# Function to get the active window title and process ID
def get_active_window_details():
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    pid = ctypes.c_ulong()
    hwnd = user32.GetForegroundWindow()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process_id = pid.value
    length = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value, process_id

# Function to format time span
def format_time_span(seconds):
    span = datetime.timedelta(seconds=seconds)
    return str(span)

# Function to connect to MySQL database
def connect_to_database():
    return mysql.connector.connect(
        host=db_config['host'],
        user=db_config['user'],
        password=db_config['password'],
        database=db_config['database'],
        port=db_config.get('port', 3306)  # Use port from config or default to 3306
    )

# Function to create the table if it doesn't exist
def create_table_if_not_exists(cursor):
    create_table_query = '''
    CREATE TABLE IF NOT EXISTS cg_timetracker (
        ID INT AUTO_INCREMENT PRIMARY KEY,
        Time_Started DATETIME,
        Duration VARCHAR(255),
        Time_Ended DATETIME,
        Application_Name VARCHAR(255),
        Window_Name VARCHAR(255),
        Project_Name VARCHAR(255),
        Client VARCHAR(255),
        Tags VARCHAR(255),
        Current_User VARCHAR(255)
    )
    '''
    cursor.execute(create_table_query)

# Function to insert data into MySQL table
def insert_into_database(cursor, log_entry):
    insert_query = '''
    INSERT INTO cg_timetracker (
        Time_Started, Duration, Time_Ended, Application_Name, Window_Name,
        Project_Name, Client, Tags, Current_User
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    '''
    cursor.execute(insert_query, (
        log_entry["Time Started"],
        log_entry["Duration"],
        log_entry["Time Ended"],
        log_entry["Application Name"],
        log_entry["Window Name"],
        log_entry["Project Name"],
        log_entry["Client"],
        log_entry["Tags"],
        log_entry["Current User"]
    ))

# Function to write data to CSV file
def write_to_csv(log_entry):
    file_exists = os.path.isfile(csv_file_path)
    with open(csv_file_path, mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow([
                "Time Started", "Duration", "Time Ended", "Application Name", "Window Name",
                "Project Name", "Client", "Tags", "Current User"
            ])
        writer.writerow([
            log_entry["Time Started"],
            log_entry["Duration"],
            log_entry["Time Ended"],
            log_entry["Application Name"],
            log_entry["Window Name"],
            log_entry["Project Name"],
            log_entry["Client"],
            log_entry["Tags"],
            log_entry["Current User"]
        ])

# Function to handle user activity
def on_move(x, y):
    global last_activity_time
    last_activity_time = datetime.datetime.now()

def on_click(x, y, button, pressed):
    global last_activity_time
    last_activity_time = datetime.datetime.now()

def on_press(key):
    global last_activity_time
    last_activity_time = datetime.datetime.now()

# Set up listeners for mouse and keyboard activity
mouse_listener = mouse.Listener(on_move=on_move, on_click=on_click)
keyboard_listener = keyboard.Listener(on_press=on_press)

mouse_listener.start()
keyboard_listener.start()

# Initialize tracking variables
start_time = datetime.datetime.now()
last_activity_time = start_time
is_active = True
paused = False
last_window_title = ""
last_process_id = 0

# Idle tracking variables
idle_start_time = None
logging_idle = False

# Get the current user's name
current_user = getpass.getuser()

# GUI setup
class TimeTrackerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Time Tracker")
        self.geometry("300x100")
        self.window_name_var = StringVar()
        self.duration_var = StringVar()

        self.create_widgets()

    def create_widgets(self):
        tk.Label(self, text="Active Window:").pack(pady=5)
        tk.Label(self, textvariable=self.window_name_var).pack(pady=5)
        tk.Label(self, text="Duration:").pack(pady=5)
        tk.Label(self, textvariable=self.duration_var).pack(pady=5)

    def update_window_info(self, window_name, duration):
        self.window_name_var.set(window_name)
        self.duration_var.set(duration)

app = TimeTrackerApp()

# Main loop to track active window and update GUI
while is_active:
    if not paused:
        active_window_title, process_id = get_active_window_details()
        current_time = datetime.datetime.now()

        if active_window_title != last_window_title or process_id != last_process_id:
            duration = (current_time - start_time).total_seconds()
            start_time = current_time

            # Prepare data for logging
            try:
                process = psutil.Process(process_id)
                application_name = process.name()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                application_name = "Unknown"

            log_entry = {
                "Time Started": current_time.strftime("%Y/%m/%d %H:%M:%S"),
                "Duration": format_time_span(duration),
                "Time Ended": current_time.strftime("%Y/%m/%d %H:%M:%S"),
                "Application Name": application_name,
                "Window Name": active_window_title if active_window_title else "Unknown",
                "Project Name": "",  # Default project_name
                "Client": "",        # Default Client
                "Tags": "",          # Default Tags
                "Current User": current_user
            }

            # Update last known window details
            last_window_title = active_window_title
            last_process_id = process_id

            # Save data to MySQL and CSV
            try:
                db = connect_to_database()
                cursor = db.cursor()
                create_table_if_not_exists(cursor)
                insert_into_database(cursor, log_entry)
                db.commit()
                cursor.close()
                db.close()
            except mysql.connector.Error as err:
                print(f"Error: {err}")

            # Always attempt to write to CSV
            try:
                write_to_csv(log_entry)
            except Exception as e:
                print(f"CSV Write Error: {e}")

            # Update GUI
            app.update_window_info(active_window_title, format_time_span(duration))
            app.update()

            last_activity_time = current_time

        # Check for user idle time
        idle_time = (current_time - last_activity_time).total_seconds()
        if idle_time > 10:
            if not logging_idle:
                idle_start_time = current_time
                logging_idle = True
        else:
            if logging_idle:
                duration = (current_time - idle_start_time).total_seconds()
                # Log idle time
                log_entry = {
                    "Time Started": idle_start_time.strftime("%Y/%m/%d %H:%M:%S"),
                    "Duration": format_time_span(duration),
                    "Time Ended": current_time.strftime("%Y/%m/%d %H:%M:%S"),
                    "Application Name": "Unknown",
                    "Window Name": "Idle",
                    "Project Name": "idle",
                    "Client": "",
                    "Tags": "idle",
                    "Current User": current_user
                }
                
                # Save idle data to MySQL and CSV
                try:
                    db = connect_to_database()
                    cursor = db.cursor()
                    create_table_if_not_exists(cursor)
                    insert_into_database(cursor, log_entry)
                    db.commit()
                    cursor.close()
                    db.close()
                except mysql.connector.Error as err:
                    print(f"Error: {err}")

                try:
                    write_to_csv(log_entry)
                except Exception as e:
                    print(f"CSV Write Error: {e}")

                logging_idle = False

        # Check every 1 second
        time.sleep(1)

app.mainloop()
