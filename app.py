import flet as ft
import sqlite3
import bcrypt
from datetime import datetime
import threading
import re
import locale

# Встановлення локалізації для української мови
try:
    locale.setlocale(locale.LC_TIME, 'uk_UA.UTF-8')
except locale.Error:
    pass

# Database connection
conn = sqlite3.connect("inventory.db", check_same_thread=False)
cursor = conn.cursor()

# Додаємо блокування для синхронізації доступу до бази даних
db_lock = threading.Lock()

# Додавання колонки subscription_status, якщо її немає
try:
    with db_lock:
        cursor.execute("ALTER TABLE users ADD COLUMN subscription_status BOOLEAN DEFAULT FALSE")
        conn.commit()
except sqlite3.OperationalError:
    pass

# Create tables
with db_lock:
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS equipment (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        serial_number TEXT UNIQUE NOT NULL,
        location TEXT,
        responsible TEXT,
        status TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL,
        role TEXT NOT NULL,
        subscription_status BOOLEAN DEFAULT FALSE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS login_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        login_time TEXT NOT NULL,
        device_info TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equipment_id INTEGER NOT NULL,
        user_email TEXT NOT NULL,
        reservation_time TEXT NOT NULL,
        priority INTEGER DEFAULT 0,
        FOREIGN KEY (equipment_id) REFERENCES equipment(id),
        FOREIGN KEY (user_email) REFERENCES users(email)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS payment_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_email TEXT NOT NULL,
        amount TEXT NOT NULL,
        payment_time TEXT NOT NULL,
        FOREIGN KEY (user_email) REFERENCES users(email)
    )
    """)
    conn.commit()

def initialize_equipment_data():
    with db_lock:
        cursor.execute("SELECT COUNT(*) FROM equipment")
        count = cursor.fetchone()[0]
        if count == 0:  # Додаємо записи лише якщо таблиця порожня
            equipment_data = [
                ("Ноутбук Dell", "SN001", "Кабінет 101", "Іванов І.Б", "Справна"),
                ("Принтер HP", "SN002", "Кабінет 102", "Петров Б.Б", "Потрібен ремонт"),
                ("Проектор Epson", "SN003", "Кабінет 103", "Сидорова К.Г", "Справна"),
                ("Монітор LG", "SN004", "Кабінет 104", "Коваленко О.А", "Справна"),
                ("Сканер Canon", "SN005", "Кабінет 105", "Григоренко С.Р", "Потрібен ремонт"),
                ("Комп'ютер Lenovo", "SN006", "Кабінет 106", "Лисенко Р.Н", "Справна")
            ]
            cursor.executemany("INSERT INTO equipment (name, serial_number, location, responsible, status) VALUES (?, ?, ?, ?, ?)", equipment_data)
            conn.commit()

def main(page: ft.Page):
    page.title = "Облік техніки"
    page.window_min_width = 500
    page.horizontal_alignment = 'center'
    page.vertical_alignment = 'center'
    page.theme_mode = 'white'
    page.padding = 20

    role = None
    current_email = None
    equipment = []

    # Button styling
    bg_color = "white"
    hover_color = "red"

    # Input fields
    email_field = ft.TextField(hint_text='Логін', width=300, color='white', border_color='white', hint_style=ft.TextStyle(color='white'))
    password_field = ft.TextField(hint_text='Пароль', password=True, can_reveal_password=True, width=300, color='white', border_color='white', hint_style=ft.TextStyle(color='white'))
    confirm_password_field = ft.TextField(hint_text='Підтвердіть пароль', password=True, can_reveal_password=True, width=300, color='white', border_color='white', hint_style=ft.TextStyle(color='white'))
    role_dropdown = ft.Dropdown(
        width=300,
        hint_text="Роль",
        options=[
            ft.dropdown.Option("student", "Студент"),
            ft.dropdown.Option("teacher", "Викладач"),
        ],
        border_color='white',
        hint_style=ft.TextStyle(color='white'),
        text_style=ft.TextStyle(color='white')
    )

    # Store previous sizes for comparison
    prev_btn_width = None
    prev_btn_height = None

    # List to store active timers
    active_timers = []

    # Flags to control timers
    stop_timers = threading.Event()

    def on_hover(e):
        e.control.bgcolor = hover_color if e.data == "true" else bg_color
        e.control.update()

    # Containers for UI elements
    text_login = ft.Container(ft.Text(value='Увійти в систему', size=25, weight='bold', color='white'), margin=ft.margin.only(left=100))
    text_register = ft.Container(ft.Text(value='Реєстрація', size=25, weight='bold', color='white'), margin=ft.margin.only(left=150))
    login_input = ft.Container(content=email_field, margin=ft.margin.only(left=50))
    senha_input = ft.Container(content=password_field, margin=ft.margin.only(left=50))
    confirm_senha_input = ft.Container(content=confirm_password_field, margin=ft.margin.only(left=50))
    role_input = ft.Container(content=role_dropdown, margin=ft.margin.only(left=50))

    btn_login = ft.Container(
        ft.ElevatedButton(text='Увійти', width=200, height=50, bgcolor=bg_color, on_hover=on_hover, on_click=lambda e: login(e), style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
        margin=ft.margin.only(left=100)
    )
    btn_register = ft.Container(
        ft.ElevatedButton(text='Зареєструватися', width=200, height=50, bgcolor=bg_color, on_hover=on_hover, on_click=lambda e: register(e), style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
        margin=ft.margin.only(left=100)
    )
    btn_to_register = ft.Container(
        ft.ElevatedButton(text='Реєстрація', width=200, height=50, bgcolor=bg_color, on_hover=on_hover, on_click=lambda e: show_register(e), style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
        margin=ft.margin.only(left=100)
    )
    btn_to_login = ft.Container(
        ft.ElevatedButton(text='Увійти', width=200, height=50, bgcolor=bg_color, on_hover=on_hover, on_click=lambda e: show_login(e), style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
        margin=ft.margin.only(left=100)
    )

    # Dynamic time text
    time_text = ft.Text(value="", size=12, italic=True, color='white')

    # Login layout
    login_layout = ft.Container(
        content=ft.Stack([
            ft.Image(src="https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg", fit=ft.ImageFit.COVER, width=600, height=600),
            ft.Column(
                spacing=30,
                alignment='center',
                controls=[
                    text_login,
                    login_input,
                    senha_input,
                    btn_login,
                    btn_to_register,
                    time_text
                ]
            )
        ]),
        width=400,
        height=400,
        border_radius=20,
        shadow=ft.BoxShadow(blur_radius=5, color='red')
    )

    # Register layout
    register_layout = ft.Container(
        content=ft.Stack([
            ft.Image(src="https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg", fit=ft.ImageFit.COVER, width=750, height=700),
            ft.Column(
                spacing=25,
                alignment='center',
                controls=[
                    text_register,
                    login_input,
                    senha_input,
                    confirm_senha_input,
                    role_input,
                    btn_register,
                    btn_to_login,
                    time_text
                ]
            )
        ]),
        width=400,
        height=500,
        border_radius=20,
        shadow=ft.BoxShadow(blur_radius=5, color='red')
    )

    content_container = ft.Column()

    def show_snackbar(message, bgcolor=None, duration=3000):
        if not stop_timers.is_set():
            page.open(ft.SnackBar(ft.Text(message, color='white'), bgcolor=bgcolor, duration=duration))
            page.update()

    def update_time():
        if stop_timers.is_set():
            return
        current_time = datetime.now().strftime("Дата і час: %H:%M EEST, %A, %d %B %Y")
        time_text.value = current_time
        if not stop_timers.is_set():
            try:
                page.update()
                timer = threading.Timer(1, update_time)
                active_timers.append(timer)
                timer.start()
            except RuntimeError:
                pass  # Handle case where page is no longer accessible

    def check_button_size():
        nonlocal prev_btn_width, prev_btn_height
        if stop_timers.is_set():
            return
        current_btn = btn_login.content
        current_width = current_btn.width
        current_height = current_btn.height

        if prev_btn_width is not None and prev_btn_height is not None:
            if current_width != prev_btn_width or current_height != prev_btn_height:
                show_snackbar(f"Розмір кнопки змінився! Новий розмір: {current_width}x{current_height}")

        prev_btn_width = current_width
        prev_btn_height = current_height
        if not stop_timers.is_set():
            try:
                timer = threading.Timer(1, check_button_size)
                active_timers.append(timer)
                timer.start()
            except RuntimeError:
                pass  # Handle case where page is no longer accessible

    def start_monitors():
        stop_timers.clear()  # Reset the stop flag
        update_time()
        check_button_size()

    def stop_monitors():
        stop_timers.set()  # Signal timers to stop
        for timer in active_timers:
            timer.cancel()  # Cancel all active timers
        active_timers.clear()  # Clear the list of timers

    def cleanup():
        stop_monitors()
        with db_lock:
            conn.close()

    def show_login(e):
        stop_monitors()  # Stop any existing timers
        content_container.controls.clear()
        content_container.controls.append(login_layout)
        start_monitors()
        email_field.value = ""
        password_field.value = ""
        page.update()

    def show_register(e):
        stop_monitors()  # Stop any existing timers
        content_container.controls.clear()
        content_container.controls.append(register_layout)
        start_monitors()
        email_field.value = ""
        password_field.value = ""
        confirm_password_field.value = ""
        role_dropdown.value = None
        page.update()

    def register(e):
        email = email_field.value
        password = password_field.value
        confirm_password = confirm_password_field.value
        selected_role = role_dropdown.value

        if not all([email, password, confirm_password, selected_role]):
            show_snackbar("Заповніть усі поля!", bgcolor="red_400")
            return

        if password != confirm_password:
            show_snackbar("Паролі не збігаються!", bgcolor="red_400")
            return

        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        try:
            with db_lock:
                cursor.execute("INSERT INTO users (email, password, role, subscription_status) VALUES (?, ?, ?, ?)",
                              (email, hashed_password, selected_role, False))
                conn.commit()
            show_snackbar("Реєстрація успішна!")
            show_login(e)
        except sqlite3.IntegrityError:
            show_snackbar("Цей email вже зареєстровано!", bgcolor="red_400")

    def login(e):
        nonlocal role, current_email
        email = email_field.value
        password = password_field.value

        if not email or not password:
            show_snackbar("Введіть email і пароль!", bgcolor="red_400")
            return

        with db_lock:
            cursor.execute("SELECT password, role FROM users WHERE email = ?", (email,))
            user = cursor.fetchone()

        if user and bcrypt.checkpw(password.encode('utf-8'), user[0].encode('utf-8')):
            role = user[1]
            current_email = email
            login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            device_info = "Unknown Device"
            with db_lock:
                cursor.execute("INSERT INTO login_logs (email, login_time, device_info) VALUES (?, ?, ?)",
                              (email, login_time, device_info))
                conn.commit()
            show_snackbar(f"Увійшли як {role}!")
            show_main_menu(e)
        elif email == "admin" and password == "admin":
            role = "admin"
            current_email = "admin"
            login_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            device_info = "Unknown Device"
            with db_lock:
                cursor.execute("INSERT INTO login_logs (email, login_time, device_info) VALUES (?, ?, ?)",
                              ("admin", login_time, device_info))
                conn.commit()
            show_snackbar("Увійшли як адміністратор!")
            show_main_menu(e)
        else:
            email_field.value = ""
            password_field.value = ""
            show_snackbar("Неправильний email або пароль!", bgcolor="red_400")

    def show_main_menu(e):
        stop_monitors()  # Stop any existing timers
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=400, height=500) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Облік техніки", size=24, weight="bold", text_align='center', color='white'),
                        ft.ElevatedButton("Додати запис", on_click=show_add_equipment, visible=role in ["teacher", "admin"], style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Показати всі записи", on_click=show_list_equipment, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Бронювати техніку", on_click=show_reserve_equipment, visible=role in ["student", "teacher"], style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Переглянути бронювання", on_click=show_reservations, visible=role in ["student", "teacher", "admin"], style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Обробити чергу бронювань", on_click=process_reservation_queue, visible=role == "admin", style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Оформити підписку", on_click=show_subscription_payment, visible=role == "student", style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Видалити запис", on_click=show_delete_equipment, visible=role == "admin", style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Переглянути користувачів та логи", on_click=show_users_and_logs, visible=role == "admin", style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Вийти", on_click=logout, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        time_text
                    ]
                )
            ]),
            width=400,
            height=500,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)
        start_monitors()
        page.update()

    def show_add_equipment(e):
        if role not in ["teacher", "admin"]:
            show_snackbar("Студенти не можуть додавати записи!")
            return

        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        # Dropdown for equipment status
        status_dropdown = ft.Dropdown(
            label="Стан",
            width=500,
            options=[
                ft.dropdown.Option("Справна", "Справна"),
                ft.dropdown.Option("Потрібен ремонт", "Потрібен ремонт"),
                ft.dropdown.Option("Списана", "Списана"),
            ],
            border_color='white',
            label_style=ft.TextStyle(color='white'),
            text_style=ft.TextStyle(color='white')
        )
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=500, height=550) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Додати техніку", size=24, weight="bold", color='white'),
                        ft.TextField(label="Назва пристрою", autofocus=True, color='white', label_style=ft.TextStyle(color='white')),
                        ft.TextField(label="Серійний номер", color='white', label_style=ft.TextStyle(color='white')),
                        ft.TextField(label="Кабінет", color='white', label_style=ft.TextStyle(color='white')),
                        ft.TextField(label="Відповідальний", color='white', label_style=ft.TextStyle(color='white')),
                        status_dropdown,
                        ft.ElevatedButton("Додати", on_click=add_equipment, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        time_text
                    ]
                )
            ]),
            width=500,
            height=550,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)
        start_monitors()
        page.update()

    def add_equipment(e):
        # Adjust indices to account for the new dropdown
        fields = content_container.controls[0].content.controls[1].controls[1:5]  # TextFields: name, serial, location, responsible
        status_dropdown = content_container.controls[0].content.controls[1].controls[5]  # Dropdown for status
        if not all(field.value for field in fields) or not status_dropdown.value:
            show_snackbar("Заповніть усі поля!")
            return

        name, serial, location, responsible = [field.value for field in fields]
        status = status_dropdown.value
        try:
            with db_lock:
                cursor.execute("INSERT INTO equipment (name, serial_number, location, responsible, status) VALUES (?, ?, ?, ?, ?)",
                               (name, serial, location, responsible, status))
                conn.commit()
            show_snackbar("Техніку додано успішно!")
            show_main_menu(e)
        except sqlite3.IntegrityError:
            show_snackbar("Серійний номер уже існує!")

    def show_list_equipment(e):
        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=800, height=450) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Перелік техніки", size=24, weight="bold", color='white')
                    ]
                )
            ]),
            width=800,
            height=450,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)
        with db_lock:
            cursor.execute("SELECT * FROM equipment")
            rows = cursor.fetchall()
        if not rows:
            layout.content.controls[1].controls.append(ft.Text("Список порожній.", color='white'))
        else:
            for row in rows:
                layout.content.controls[1].controls.append(
                    ft.Text(f"ID: {row[0]}, Назва: {row[1]}, SN: {row[2]}, Кабінет: {row[3]}, Відповідальний: {row[4]}, Стан: {row[5]}", color='white')
                )
        layout.content.controls[1].controls.append(ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))))
        layout.content.controls[1].controls.append(time_text)
        start_monitors()
        page.update()

    def show_delete_equipment(e):
        if role != "admin":
            show_snackbar("Тільки адміністратор може видаляти записи!")
            return

        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=850, height=600) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Видалити техніку", size=24, weight="bold", text_align='center', color='white')
                    ]
                )
            ]),
            width=850,
            height=600,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)

        with db_lock:
            cursor.execute("SELECT * FROM equipment")
            rows = cursor.fetchall()

        if not rows:
            layout.content.controls[1].controls.append(ft.Text("Список порожній.", color='white'))
        else:
            data_table = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("ID", color='white')),
                    ft.DataColumn(ft.Text("Назва", color='white')),
                    ft.DataColumn(ft.Text("Серійний номер", color='white')),
                    ft.DataColumn(ft.Text("Кабінет", color='white')),
                    ft.DataColumn(ft.Text("Відповідальний", color='white')),
                    ft.DataColumn(ft.Text("Стан", color='white')),
                    ft.DataColumn(ft.Text("Дія", color='white')),
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(row[0]), color='white')),
                            ft.DataCell(ft.Text(row[1], color='white')),
                            ft.DataCell(ft.Text(row[2], color='white')),
                            ft.DataCell(ft.Text(row[3], color='white')),
                            ft.DataCell(ft.Text(row[4], color='white')),
                            ft.DataCell(ft.Text(row[5], color='white')),
                            ft.DataCell(
                                ft.ElevatedButton(
                                    text="Видалити",
                                    on_click=lambda e, serial=row[2]: delete_equipment(serial),
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))
                                )
                            ),
                        ]
                    ) for row in rows
                ]
            )
            layout.content.controls[1].controls.append(
                ft.ListView(
                    controls=[data_table],
                    auto_scroll=True,
                    width=800,
                    height=400
                )
            )

        layout.content.controls[1].controls.append(ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))))
        layout.content.controls[1].controls.append(time_text)
        start_monitors()
        page.update()

    def delete_equipment(serial):
        with db_lock:
            cursor.execute("DELETE FROM equipment WHERE serial_number = ?", (serial,))
            conn.commit()
            rowcount = cursor.rowcount
        if rowcount:
            show_snackbar("Видалено!")
        else:
            show_snackbar("Пристрій не знайдено!")
        show_delete_equipment(None)

    def show_users_and_logs(e):
        if role != "admin":
            show_snackbar("Тільки адміністратор може переглядати користувачів та логи!")
            return

        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""

        # Ініціалізація контейнерів перед додаванням до controls
        user_section = ft.Container(visible=False)
        login_logs_section = ft.Container(visible=False)
        payment_logs_section = ft.Container(visible=False)

        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=650, height=500) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    horizontal_alignment='center',
                    controls=[
                        ft.Text("Користувачі та логи", size=24, weight="bold", text_align='center', color='white'),
                        ft.Row(
                            alignment=ft.MainAxisAlignment.CENTER,
                            controls=[
                                ft.ElevatedButton(
                                    text="Зареєстровані користувачі",
                                    on_click=lambda e: show_section("users"),
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(color='black')),
                                    width=200
                                ),
                                ft.ElevatedButton(
                                    text="Логи входу",
                                    on_click=lambda e: show_section("login_logs"),
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(color='black')),
                                    width=200
                                ),
                                ft.ElevatedButton(
                                    text="Логи платежів",
                                    on_click=lambda e: show_section("payment_logs"),
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(color='black')),
                                    width=200
                                )
                            ],
                            spacing=10
                        ),
                        user_section,
                        login_logs_section,
                        payment_logs_section
                    ]
                )
            ]),
            width=650,
            height=500,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)

        # Fetch all users
        with db_lock:
            cursor.execute("SELECT email, password, role, subscription_status FROM users")
            users = cursor.fetchall()

        # Fetch all login logs
        with db_lock:
            cursor.execute("SELECT email, login_time, device_info FROM login_logs")
            logs = cursor.fetchall()

        # Fetch all payment logs
        with db_lock:
            cursor.execute("SELECT user_email, amount, payment_time FROM payment_logs")
            payments = cursor.fetchall()

        def show_section(section):
            nonlocal user_section, login_logs_section, payment_logs_section
            user_section.visible = section == "users"
            login_logs_section.visible = section == "login_logs"
            payment_logs_section.visible = section == "payment_logs"

            if section == "users" and users:
                user_table = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Email", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Пароль (хеш)", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Роль", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Статус підписки", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Дія", text_align='center', color='white')),
                    ],
                    rows=[
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(user[0], text_align='center', color='white')),
                                ft.DataCell(ft.Text(user[1][:5] if user[1] else "", text_align='center', color='white')),
                                ft.DataCell(ft.Text(user[2], text_align='center', color='white')),
                                ft.DataCell(ft.Text("Активна" if user[3] else "Відсутня", text_align='center', color='white')),
                                ft.DataCell(
                                    ft.ElevatedButton(
                                        text="Видалити",
                                        on_click=lambda e, email=user[0]: delete_user(email),
                                        style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))
                                    )
                                ),
                            ]
                        ) for user in users
                    ],
                    column_spacing=10,
                )
                user_section.content = ft.Column([
                    ft.Text("Зареєстровані користувачі", size=18, weight="bold", text_align='center', color='white'),
                    ft.ListView(
                        controls=[user_table],
                        auto_scroll=True,
                        width=500,
                        height=200
                    )
                ])
            elif section == "users" and not users:
                user_section.content = ft.Text("Немає зареєстрованих користувачів.", text_align='center', color='white')

            if section == "login_logs" and logs:
                log_table = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Email", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Час входу", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Пристрій", text_align='center', color='white')),
                    ],
                    rows=[
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(log[0], text_align='center', color='white')),
                                ft.DataCell(ft.Text(log[1], text_align='center', color='white')),
                                ft.DataCell(ft.Text(log[2], text_align='center', color='white')),
                            ]
                        ) for log in logs
                    ],
                    column_spacing=10,
                )
                login_logs_section.content = ft.Column([
                    ft.Text("Логи входу", size=18, weight="bold", text_align='center', color='white'),
                    ft.ListView(
                        controls=[log_table],
                        auto_scroll=True,
                        width=500,
                        height=200
                    )
                ])
            elif section == "login_logs" and not logs:
                login_logs_section.content = ft.Text("Немає логів входу.", text_align='center', color='white')

            if section == "payment_logs" and payments:
                payment_table = ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Email", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Сума", text_align='center', color='white')),
                        ft.DataColumn(ft.Text("Час оплати", text_align='center', color='white')),
                    ],
                    rows=[
                        ft.DataRow(
                            cells=[
                                ft.DataCell(ft.Text(payment[0], text_align='center', color='white')),
                                ft.DataCell(ft.Text(payment[1], text_align='center', color='white')),
                                ft.DataCell(ft.Text(payment[2], text_align='center', color='white')),
                            ]
                        ) for payment in payments
                    ],
                    column_spacing=10,
                )
                payment_logs_section.content = ft.Column([
                    ft.Text("Логи платежів", size=18, weight="bold", text_align='center', color='white'),
                    ft.ListView(
                        controls=[payment_table],
                        auto_scroll=True,
                        width=500,
                        height=200
                    )
                ])
            elif section == "payment_logs" and not payments:
                payment_logs_section.content = ft.Text("Немає логів платежів.", text_align='center', color='white')

            if not stop_timers.is_set():
                page.update()

        # Show users section by default
        show_section("users")

        layout.content.controls[1].controls.append(
            ft.Container(
                content=ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                alignment=ft.alignment.center
            )
        )
        layout.content.controls[1].controls.append(
            ft.Container(
                content=time_text,
                alignment=ft.alignment.center
            )
        )
        start_monitors()
        page.update()

    def delete_user(email):
        if email == "admin":
            show_snackbar("Ви не можете видалити свій акаунт!", bgcolor="red_400")
            return
        
        with db_lock:
            cursor.execute("DELETE FROM login_logs WHERE email = ?", (email,))
            cursor.execute("DELETE FROM reservations WHERE user_email = ?", (email,))
            cursor.execute("DELETE FROM payment_logs WHERE user_email = ?", (email,))
            cursor.execute("DELETE FROM users WHERE email = ?", (email,))
            conn.commit()
            rowcount = cursor.rowcount
        if rowcount:
            show_snackbar("Акаунт видалено!")
        else:
            show_snackbar("Користувача не знайдено!")
        show_users_and_logs(None)

    def show_reserve_equipment(e):
        if role not in ["student", "teacher"]:
            show_snackbar("Тільки студенти та викладачі можуть бронювати техніку!")
            return

        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=500, height=400) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Бронювання техніки", size=24, weight="bold", color='white'),
                        ft.TextField(label="ID обладнання", autofocus=True, color='white', label_style=ft.TextStyle(color='white')),
                        ft.ElevatedButton("Забронювати", on_click=reserve_equipment, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        time_text
                    ]
                )
            ]),
            width=500,
            height=400,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)
        start_monitors()
        page.update()

    def reserve_equipment(e):
        if role not in ["student", "teacher"]:
            show_snackbar("Тільки студенти та викладачі можуть бронювати техніку!")
            return

        equipment_id_field = content_container.controls[0].content.controls[1].controls[1].value
        reservation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if not equipment_id_field:
            show_snackbar("Введіть ID обладнання!")
            return

        with db_lock:
            cursor.execute("SELECT id FROM equipment WHERE id = ?", (equipment_id_field,))
            equipment_exists = cursor.fetchone()

        if not equipment_exists:
            show_snackbar("Обладнання не знайдено!")
            return

        priority = 0
        if role == "teacher":
            priority = 2
        elif role == "student":
            with db_lock:
                cursor.execute("SELECT subscription_status FROM users WHERE email = ?", (current_email,))
                subscription_status = cursor.fetchone()[0]
            priority = 1 if subscription_status else 0

        try:
            with db_lock:
                cursor.execute("""
                    INSERT INTO reservations (equipment_id, user_email, reservation_time, priority)
                    VALUES (?, ?, ?, ?)
                """, (equipment_id_field, current_email, reservation_time, priority))
                conn.commit()
            show_snackbar("Бронювання створено!")
            show_main_menu(e)
        except sqlite3.Error as err:
            show_snackbar(f"Помилка: {str(err)}")

    def show_reservations(e):
        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=600, height=450) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Список бронювань", size=24, weight="bold", color='white')
                    ]
                )
            ]),
            width=600,
            height=450,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)

        with db_lock:
            if role == "admin":
                cursor.execute("SELECT r.id, r.equipment_id, r.user_email, r.reservation_time, r.priority, e.name FROM reservations r JOIN equipment e ON r.equipment_id = e.id")
            else:
                cursor.execute("SELECT r.id, r.equipment_id, r.user_email, r.reservation_time, r.priority, e.name FROM reservations r JOIN equipment e ON r.equipment_id = e.id WHERE r.user_email = ?", (current_email,))
            rows = cursor.fetchall()

        if not rows:
            layout.content.controls[1].controls.append(ft.Text("Немає бронювань.", color='white'))
        else:
            data_table = ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("ID", color='white')),
                    ft.DataColumn(ft.Text("Обладнання", color='white')),
                    ft.DataColumn(ft.Text("Користувач", color='white')),
                    ft.DataColumn(ft.Text("Час бронювання", color='white')),
                    ft.DataColumn(ft.Text("Пріоритет", color='white')),
                    ft.DataColumn(ft.Text("Дія", color='white')),
                ],
                rows=[
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(row[0]), color='white')),
                            ft.DataCell(ft.Text(row[5], color='white')),
                            ft.DataCell(ft.Text(row[2], color='white')),
                            ft.DataCell(ft.Text(row[3], color='white')),
                            ft.DataCell(ft.Text(str(row[4]), color='white')),
                            ft.DataCell(
                                ft.ElevatedButton(
                                    text="Скасувати",
                                    on_click=lambda e, res_id=row[0]: cancel_reservation(res_id),
                                    visible=role == "admin" or row[2] == current_email,
                                    style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))
                                )
                            ),
                        ]
                    ) for row in rows
                ]
            )
            layout.content.controls[1].controls.append(
                ft.ListView(
                    controls=[data_table],
                    auto_scroll=True,
                    width=800,
                    height=400
                )
            )

        layout.content.controls[1].controls.append(ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))))
        layout.content.controls[1].controls.append(time_text)
        start_monitors()
        page.update()

    def cancel_reservation(res_id):
        with db_lock:
            cursor.execute("DELETE FROM reservations WHERE id = ?", (res_id,))
            conn.commit()
            rowcount = cursor.rowcount
        if rowcount:
            show_snackbar("Бронювання скасовано!")
        else:
            show_snackbar("Бронювання не знайдено!")
        show_reservations(None)

    def process_reservation_queue(e):
        if role != "admin":
            show_snackbar("Тільки адміністратор може обробляти чергу!")
            return

        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=500, height=400) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Обробка черги бронювань", size=24, weight="bold", color='white'),
                        ft.TextField(label="ID обладнання", autofocus=True, color='white', label_style=ft.TextStyle(color='white')),
                        ft.ElevatedButton("Обробити", on_click=lambda e: process_queue_for_equipment(e), style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        time_text
                    ]
                )
            ]),
            width=500,
            height=400,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)
        start_monitors()
        page.update()

    def process_queue_for_equipment(e):
        equipment_id = content_container.controls[0].content.controls[1].controls[1].value
        if not equipment_id:
            show_snackbar("Введіть ID обладнання!")
            return

        with db_lock:
            cursor.execute("SELECT id FROM equipment WHERE id = ?", (equipment_id,))
            equipment_exists = cursor.fetchone()

        if not equipment_exists:
            show_snackbar("Обладнання не знайдено!")
            return

        with db_lock:
            cursor.execute("""
                SELECT user_email, reservation_time, priority
                FROM reservations
                WHERE equipment_id = ?
                ORDER BY priority DESC, reservation_time ASC
            """, (equipment_id,))
            reservations = cursor.fetchall()

        if reservations:
            selected_user = reservations[0][0]
            show_snackbar(f"Техніку заброньовано для {selected_user}!")
            with db_lock:
                cursor.execute("DELETE FROM reservations WHERE user_email = ? AND equipment_id = ?",
                              (selected_user, equipment_id))
                conn.commit()
        else:
            show_snackbar("Немає бронювань для цього обладнання.")
        show_main_menu(e)

    def show_subscription_payment(e):
        if role != "student":
            show_snackbar("Тільки студенти можуть оформлювати підписку!")
            return

        with db_lock:
            cursor.execute("SELECT subscription_status FROM users WHERE email = ?", (current_email,))
            subscription_status = cursor.fetchone()[0]
        if subscription_status:
            show_snackbar("У вас уже є активна підписка!")
            return

        stop_monitors()
        content_container.controls.clear()
        background_image = "https://st.depositphotos.com/1000350/2282/i/450/depositphotos_22823894-stock-photo-dark-concrete-texture.jpg" if role in ["student", "teacher", "admin"] else ""
        layout = ft.Container(
            content=ft.Stack([
                ft.Image(src=background_image, fit=ft.ImageFit.COVER, width=600, height=500) if background_image else ft.Container(),
                ft.Column(
                    spacing=20,
                    alignment='center',
                    controls=[
                        ft.Text("Оплата підписки", size=24, weight="bold", color='white'),
                        ft.TextField(label="Номер карти (16 цифр)", max_length=16, keyboard_type=ft.KeyboardType.NUMBER, color='white', label_style=ft.TextStyle(color='white')),
                        ft.TextField(label="Термін дії (MM/YY)", max_length=5, color='white', label_style=ft.TextStyle(color='white')),
                        ft.TextField(label="CVV (3 цифри)", max_length=3, keyboard_type=ft.KeyboardType.NUMBER, password=True, color='white', label_style=ft.TextStyle(color='white')),
                        ft.TextField(label="Сума (грн)", value="100", read_only=True, color='white', label_style=ft.TextStyle(color='white')),
                        ft.ElevatedButton("Оплатити", on_click=process_payment, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        ft.ElevatedButton("Назад", on_click=show_main_menu, style=ft.ButtonStyle(text_style=ft.TextStyle(color='black'))),
                        time_text
                    ]
                )
            ]),
            width=600,
            height=500,
            border_radius=20,
            shadow=ft.BoxShadow(blur_radius=5, color='red')
        )
        content_container.controls.append(layout)
        start_monitors()
        page.update()

    def process_payment(e):
        card_number = content_container.controls[0].content.controls[1].controls[1].value
        expiry_date = content_container.controls[0].content.controls[1].controls[2].value
        cvv = content_container.controls[0].content.controls[1].controls[3].value
        amount = content_container.controls[0].content.controls[1].controls[4].value

        if not (card_number.isdigit() and len(card_number) == 16 and validate_luhn(card_number)):
            show_snackbar("Неправильний номер карти!", bgcolor="red_400")
            return

        if not re.match(r"^(0[1-9]|1[0-2])\/[0-9]{2}$", expiry_date):
            show_snackbar("Неправильний формат терміну дії (MM/YY)!", bgcolor="red_400")
            return
        month, year = map(int, expiry_date.split("/"))
        current_year = datetime.now().year % 100
        current_month = datetime.now().month
        if year < current_year or (year == current_year and month < current_month):
            show_snackbar("Картка прострочена!", bgcolor="red_400")
            return

        if not (cvv.isdigit() and len(cvv) == 3):
            show_snackbar("Неправильний CVV!", bgcolor="red_400")
            return

        try:
            with db_lock:
                cursor.execute("UPDATE users SET subscription_status = TRUE WHERE email = ?", (current_email,))
                conn.commit()

                payment_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cursor.execute("INSERT INTO payment_logs (user_email, amount, payment_time) VALUES (?, ?, ?)",
                              (current_email, amount, payment_time))
                conn.commit()

            show_snackbar("Оплата успішна! Підписка активована.")
            show_main_menu(e)
        except sqlite3.Error as err:
            show_snackbar(f"Помилка: {str(err)}", bgcolor="red_400")

    def validate_luhn(card_number):
        digits = [int(d) for d in card_number]
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = sum(odd_digits)
        for d in even_digits:
            checksum += sum(divmod(d * 2, 10))
        return checksum % 10 == 0

    def logout(e):
        nonlocal role, current_email
        role = None
        current_email = None
        show_snackbar("Ви вийшли з системи!")
        show_login(e)

    # Initial screen
    initialize_equipment_data()  # Додаємо початкові дані про техніку
    content_container.controls.append(login_layout)
    page.add(content_container)
    start_monitors()
    page.on_close = cleanup  # Cleanup on app close
    page.update()

ft.app(target=main, view=ft.AppView.WEB_BROWSER, host="192.168.1.7", port=8080)
