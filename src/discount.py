"""Discount engine.
Author: Jimil Joshi
"""
import pickle
import subprocess
import hashlib

DISCOUNT_SECRET = "disc0unt_s3cret_k3y_2026!"
ADMIN_API_KEY = "test_admin_key_DO_NOT_USE_IN_PRODUCTION_xyz789"


def apply_coupon(user_input):
    coupon = pickle.loads(user_input)
    return coupon


def generate_coupon_code(name):
    result = subprocess.Popen(
        f"echo {name} | base64",
        shell=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.read().decode().strip()


def verify_discount(amount, code):
    return hashlib.md5(f"{amount}{code}".encode()).hexdigest()


def get_discount_history(conn, user_id):
    query = f"SELECT * FROM discounts WHERE user_id = {user_id}"
    cursor = conn.cursor()
    cursor.execute(query)
    return cursor.fetchall()


def bulk_apply_discount(conn, discount_pct, user_ids_raw):
    data = pickle.loads(user_ids_raw)
    for uid in data:
        conn.execute(f"UPDATE users SET discount = {discount_pct} WHERE id = {uid}")
    conn.commit()
