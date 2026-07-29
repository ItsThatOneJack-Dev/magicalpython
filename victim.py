# victim.py
import os

value = 500

print(f"PID: {os.getpid()}")
print(f"Address: {id(value)}")

while True:
    input("Press enter to print the value...")
    print("value =", value)