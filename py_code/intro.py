from flask import Flask, render_template, request, redirect, url_for, session
import mysql.connector
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os
import random
import string
import time
from sklearn.linear_model import LinearRegression
from flask_mail import Mail, Message

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Email configuration for OTP
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'your_email@gmail.com'  # Replace with your email
app.config['MAIL_PASSWORD'] = 'your_email_password'  # Replace with your email password
mail = Mail(app)

# MySQL connection
conn = mysql.connector.connect(
    host="localhost",
    user="root",
    password="1234",
    database="carsales"
)
cursor = conn.cursor(dictionary=True)


# Generate random OTP
def generate_otp(length=6):
    return ''.join(random.choices(string.digits, k=length))


# Send OTP via email
def send_otp_email(email, otp):
    try:
        msg = Message('Your OTP for Car Sales Login', sender='your_email@gmail.com', recipients=[email])
        msg.body = f'Your OTP for login is: {otp}\nThis OTP is valid for 5 minutes.'
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False


@app.route('/')
def home():
    session.clear()
    return render_template('Login.html')


@app.route("/Confirm", methods=['POST', 'GET'])
def base():
    name = request.form.get('Uname')
    key = request.form.get('pass')

    if key == 'ultron':
        # Generate and store OTP
        otp = generate_otp()
        session['otp'] = otp
        session['otp_created'] = int(time.time())
        session['otp_verified'] = False
        session['username'] = name

        # For demo purposes, we'll just print the OTP
        # In production, you would send this to the user's email/phone
        print(f"Generated OTP for {name}: {otp}")  # Remove this in production

        # Store the intended role for after OTP verification
        if name == 'Admin':
            session['pending_role'] = 'admin'
        else:
            session['pending_role'] = 'user'

        return redirect(url_for('verify_otp'))
    else:
        return render_template('Login.html', error="Invalid username or password!")


@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if 'username' not in session:
        return redirect(url_for('home'))

    # Check if OTP has expired (5 minutes)
    if 'otp_created' in session and (int(time.time()) - session['otp_created'] > 300):
        session.clear()
        return render_template('Login.html', error="OTP has expired. Please login again.")

    if request.method == 'POST':
        user_otp = request.form.get('otp')

        if 'otp' in session and user_otp == session['otp']:
            session['otp_verified'] = True
            session['logged_in'] = True
            session['role'] = session.pop('pending_role', 'user')

            if session['role'] == 'admin':
                return render_template('Base.html')
            else:
                return redirect(url_for('purchase'))
        else:
            return render_template('otp_verification.html', error="Invalid OTP. Please try again.")

    return render_template('otp_verification.html')


@app.route('/purchase')
def purchase():
    if not session.get('logged_in') or not session.get('otp_verified'):
        return redirect(url_for('home'))

    cursor.execute("SELECT * FROM carmodels")
    cars = cursor.fetchall()
    return render_template('purchase.html', cars=cars)


@app.route('/Compare')
def compare():
    if not session.get('logged_in') or not session.get('otp_verified') or session.get('role') != 'admin':
        return redirect(url_for('home'))
    return render_template('compare.html')


@app.route('/dashboard')
def admin_dashboard():
    if not session.get('logged_in') or not session.get('otp_verified') or session.get('role') != 'admin':
        return redirect(url_for('home'))
    return render_template('Base.html')


@app.route('/purchase/<int:car_id>')
def customer_details(car_id):
    if not session.get('logged_in') or not session.get('otp_verified'):
        return redirect(url_for('home'))
    return render_template('customer_details.html', car_id=car_id)


@app.route('/submit_purchase', methods=['POST'])
def submit_purchase():
    if not session.get('logged_in') or not session.get('otp_verified'):
        return redirect(url_for('home'))

    car_id = int(request.form.get('car_id'))
    name = request.form.get('name')
    phone = request.form.get('phone')
    email = request.form.get('email')
    city = request.form.get('address')

    cursor.execute("SELECT MAX(order_id) FROM orders")
    result = cursor.fetchone()
    new_id = result['MAX(order_id)'] + 1 if result['MAX(order_id)'] else 1

    cursor.execute("""
        INSERT INTO orders (order_id, car_id, customer_name, customer_city, contact_no, purchase_date, email)
        VALUES (%s, %s, %s, %s, %s, CURDATE(), %s)
    """, (new_id, car_id, name, city, phone, email))
    conn.commit()

    cursor.execute("""
        SELECT car_name, car_model, vehicle_type, price, image_url 
        FROM carmodels 
        WHERE car_id = %s
    """, (car_id,))
    car = cursor.fetchone()

    session.clear()
    return render_template('confirmation.html', name=name, car=car)


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))


@app.route('/login')
def login():
    return render_template('Login.html')


@app.route('/sales', methods=['GET', 'POST'])
def sales():
    if not session.get('logged_in') or not session.get('otp_verified') or session.get('role') != 'admin':
        return redirect(url_for('home'))

    cursor.execute("SELECT DISTINCT car_name FROM carmodels ORDER BY car_name")
    brands = [row['car_name'] for row in cursor.fetchall()]

    selected_brand = request.form.get('car_brand')
    selected_model = request.form.get('car_model')
    models = []

    if selected_brand:
        cursor.execute("SELECT DISTINCT car_model FROM carmodels WHERE car_name = %s ORDER BY car_model",
                       (selected_brand,))
        models = [row['car_model'] for row in cursor.fetchall()]

    if request.method == 'POST' and selected_brand and selected_model:
        query = """
            SELECT o.purchase_date AS sale_date, c.price 
            FROM orders o
            JOIN carmodels c ON o.car_id = c.car_id
            WHERE c.car_name = %s AND c.car_model = %s
        """
        df = pd.read_sql(query, conn, params=(selected_brand, selected_model))

        if df.empty:
            return render_template("graph.html", no_data=True, car_model=f"{selected_brand} - {selected_model}")

        # Time series line chart (forecast)
        df['month'] = pd.to_datetime(df['sale_date']).dt.to_period('M').astype(str)
        monthly_sales = df.groupby('month')['price'].sum().reset_index()
        monthly_sales['month_index'] = range(len(monthly_sales))

        model = LinearRegression()
        model.fit(monthly_sales[['month_index']], monthly_sales['price'])

        future_indexes = [[i] for i in range(len(monthly_sales), len(monthly_sales) + 3)]
        predictions = model.predict(future_indexes)

        future_months = pd.date_range(
            start=pd.to_datetime(monthly_sales['month'].iloc[-1]) + pd.offsets.MonthBegin(),
            periods=3,
            freq='MS'
        ).strftime('%Y-%m')

        # Line graph
        plt.figure(figsize=(10, 5))
        ax = plt.gca()
        ax.plot(monthly_sales['month'], monthly_sales['price'], label='Actual Sales', marker='o')
        ax.plot(future_months, predictions, label='Predicted Sales', linestyle='--', marker='x')
        ax.set_xlabel('Month')
        ax.set_ylabel('Total Sales')
        ax.set_title(f"Sales Forecast for {selected_brand} - {selected_model}")
        ax.yaxis.set_major_locator(ticker.MaxNLocator(integer=True))
        ax.legend(loc='upper right')
        plt.xticks(rotation=45)
        plt.tight_layout()
        graph_path = os.path.join('static', 'graph.png')
        plt.savefig(graph_path)
        plt.close()

        # Bar chart for city-wise sales
        city_query = """
            SELECT o.customer_city, COUNT(*) AS total_sales
            FROM orders o
            JOIN carmodels c ON o.car_id = c.car_id
            WHERE c.car_name = %s AND c.car_model = %s
            GROUP BY o.customer_city
        """
        city_df = pd.read_sql(city_query, conn, params=(selected_brand, selected_model))

        plt.figure(figsize=(10, 5))
        plt.bar(city_df['customer_city'], city_df['total_sales'], color='teal')
        plt.xlabel('City')
        plt.ylabel('Total Sales')
        plt.title(f"Sales by City for {selected_brand} - {selected_model}")
        plt.xticks(rotation=45)
        plt.tight_layout()
        bar_path = os.path.join('static', 'bargraph.png')
        plt.savefig(bar_path)
        plt.close()

        return render_template('graph.html',
                               graph_url=graph_path,
                               bar_url=bar_path,
                               car_model=f"{selected_brand} - {selected_model}")

    return render_template('sales.html', brands=brands, models=models, selected_brand=selected_brand)


if __name__ == '__main__':
    app.run(debug=True)