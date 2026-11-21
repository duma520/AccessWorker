import os
import sys
import sqlite3
import shutil
import datetime
import json
import re
import time
import random
import zipfile
import pytz
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QLabel, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem,
                            QTabWidget, QCheckBox, QSpinBox, QComboBox, QMessageBox,
                            QDialog, QDialogButtonBox, QGridLayout, QGroupBox, QFileDialog,
                            QHeaderView, QMenu, QAction, QInputDialog, QSystemTrayIcon,
                            QListWidget, QListWidgetItem, QDateTimeEdit, QProgressBar,
                            QFormLayout
                            )
from PyQt5.QtCore import Qt, QTimer, QSize, QDateTime, QSettings, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QColor
from pypinyin import lazy_pinyin

# 数据库初始化
def init_db(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # 确保没有未完成的事务
        conn.commit()
        
        # 检查并添加缺失的列（非破坏性修改）
        cursor.execute("PRAGMA table_info(urls)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'success_count' not in columns:
            cursor.execute("ALTER TABLE urls ADD COLUMN success_count INTEGER DEFAULT 0")
        if 'failure_count' not in columns:
            cursor.execute("ALTER TABLE urls ADD COLUMN failure_count INTEGER DEFAULT 0")
            
        cursor.execute("PRAGMA table_info(proxies)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'success_count' not in columns:
            cursor.execute("ALTER TABLE proxies ADD COLUMN success_count INTEGER DEFAULT 0")
        if 'failure_count' not in columns:
            cursor.execute("ALTER TABLE proxies ADD COLUMN failure_count INTEGER DEFAULT 0")
            
        conn.commit()

        # 创建网址表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()
        
        # 创建代理表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proxy_type TEXT NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        conn.commit()
        
        # 创建访问记录表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS access_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url_id INTEGER NOT NULL,
            proxy_id INTEGER,
            success BOOLEAN,
            response_time REAL,
            status_code INTEGER,
            accessed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(url_id) REFERENCES urls(id),
            FOREIGN KEY(proxy_id) REFERENCES proxies(id)
        )
        ''')
        conn.commit()
        
        # 创建设置表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        ''')
        conn.commit()

        # 添加无人值守默认设置
        default_settings = [
            ('auto_crawl_enabled', '0'),
            ('auto_crawl_interval', '60'),  # 分钟
            ('auto_access_enabled', '0'),
            ('auto_access_interval', '30'),  # 分钟
            ('execution_order', '0')  # 0=先爬取后访问,1=先访问后爬取,2=同时进行
        ]
        
        cursor.executemany(
            'INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)',
            default_settings
        )
        conn.commit()
        
        # 创建代理网站表
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS proxy_sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL,
            enabled BOOLEAN DEFAULT 1,
            success_count INTEGER DEFAULT 0,
            failure_count INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # 添加非破坏性修改检查（在已有代码后面添加）
        cursor.execute("PRAGMA table_info(proxy_sites)")
        columns = [col[1] for col in cursor.fetchall()]
        if 'success_count' not in columns:
            cursor.execute("ALTER TABLE proxy_sites ADD COLUMN success_count INTEGER DEFAULT 0")
        if 'failure_count' not in columns:
            cursor.execute("ALTER TABLE proxy_sites ADD COLUMN failure_count INTEGER DEFAULT 0")
        conn.commit()


        # 启用WAL模式
        cursor.execute('PRAGMA journal_mode=WAL')
        conn.commit()
        
    except sqlite3.Error as e:
        conn.rollback()
        raise e
    
    return conn


class ProjectInfo:
    """项目信息元数据（集中管理所有项目相关信息）"""
    VERSION = "2.8.0"
    BUILD_DATE = "2025-06-28"
    AUTHOR = "杜玛"
    LICENSE = "MIT"
    COPYRIGHT = "© 永久 杜玛"
    URL = "https://github.com/duma520"
    MAINTAINER_EMAIL = "不提供"
    NAME = "网址访问量模拟工具"
    DESCRIPTION = """网址访问量模拟工具
主要功能：


"""


    VERSION_HISTORY = {
        "1.1.0": "",
        "2.2.0": "",
        "1.3.0": ""
    }
    HELP_TEXT = """
基本操作指南：



"""


    @classmethod
    def get_metadata(cls) -> dict:
        """获取主要元数据字典"""
        return {
            'version': cls.VERSION,
            'author': cls.AUTHOR,
            'license': cls.LICENSE,
            'url': cls.URL
        }


    @classmethod
    def get_header(cls) -> str:
        """生成标准化的项目头信息"""
        return f"{cls.NAME} {cls.VERSION} | {cls.LICENSE} License | {cls.URL}"



    @classmethod
    def get_about_info(cls):
        """获取ABOUT信息字典"""
        return {
            "name": cls.NAME,
            "version": cls.VERSION,
            "build_date": cls.BUILD_DATE,
            "author": cls.AUTHOR,
            "license": cls.LICENSE,
            "copyright": cls.COPYRIGHT,
            "url": cls.URL,
            "description": cls.DESCRIPTION,
            "features": [
                "",
                "",
                "",
                "",
                "",
                ""
            ]
        }

# 马卡龙色系定义
class MacaronColors_12:
    # 粉色系
    SAKURA_PINK = QColor('#FFB7CE')  # 樱花粉
    ROSE_PINK = QColor('#FF9AA2')    # 玫瑰粉
    # 蓝色系
    SKY_BLUE = QColor('#A2E1F6')     # 天空蓝
    LILAC_MIST = QColor('#E6E6FA')   # 淡丁香
    # 绿色系
    MINT_GREEN = QColor('#B5EAD7')   # 薄荷绿
    APPLE_GREEN = QColor('#D4F1C7')  # 苹果绿
    # 黄色/橙色系
    LEMON_YELLOW = QColor('#FFEAA5') # 柠檬黄
    BUTTER_CREAM = QColor('#FFF8B8') # 奶油黄
    PEACH_ORANGE = QColor('#FFDAC1') # 蜜桃橙
    # 紫色系
    LAVENDER = QColor('#C7CEEA')     # 薰衣草紫
    TARO_PURPLE = QColor('#D8BFD8')  # 香芋紫
    # 中性色
    CARAMEL_CREAM = QColor('#F0E6DD') # 焦糖奶霜

# 备份管理类
class BackupManager:
    def __init__(self, app_dir, max_backups=30):
        self.backup_dir = os.path.join(app_dir, 'backups')
        self.max_backups = max_backups
        os.makedirs(self.backup_dir, exist_ok=True)
    
    def create_backup(self, db_path, backup_type='manual'):
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"{backup_type}_{timestamp}.zip"
        backup_path = os.path.join(self.backup_dir, backup_name)
        
        # 使用WAL模式备份
        try:
            with zipfile.ZipFile(backup_path, 'w') as zipf:
                # 复制主数据库文件
                zipf.write(db_path, os.path.basename(db_path))
                
                # 复制WAL和SHM文件
                wal_file = db_path + '-wal'
                shm_file = db_path + '-shm'
                if os.path.exists(wal_file):
                    zipf.write(wal_file, os.path.basename(wal_file))
                if os.path.exists(shm_file):
                    zipf.write(shm_file, os.path.basename(shm_file))
                
                # 添加元数据
                metadata = {
                    'backup_type': backup_type,
                    'timestamp': timestamp,
                    'db_version': self.get_db_version(db_path),
                    'size': os.path.getsize(db_path)
                }
                zipf.writestr('metadata.json', json.dumps(metadata))
            
            # 清理旧备份
            self.cleanup_old_backups()
            return True, backup_path
        except Exception as e:
            return False, str(e)
    
    def get_db_version(self, db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute('PRAGMA user_version')
            version = cursor.fetchone()[0]
            conn.close()
            return version
        except:
            return 0
    
    def cleanup_old_backups(self):
        backups = self.list_backups()
        if len(backups) > self.max_backups:
            # 按时间排序，删除最旧的
            backups.sort(key=lambda x: x['timestamp'])
            for backup in backups[:len(backups)-self.max_backups]:
                try:
                    os.remove(backup['path'])
                except:
                    pass
    
    def list_backups(self):
        backups = []
        for filename in os.listdir(self.backup_dir):
            if filename.endswith('.zip'):
                path = os.path.join(self.backup_dir, filename)
                try:
                    with zipfile.ZipFile(path, 'r') as zipf:
                        if 'metadata.json' in zipf.namelist():
                            with zipf.open('metadata.json') as f:
                                metadata = json.load(f)
                                backups.append({
                                    'path': path,
                                    'filename': filename,
                                    'type': metadata.get('backup_type', 'unknown'),
                                    'timestamp': metadata.get('timestamp', ''),
                                    'size': metadata.get('size', 0),
                                    'db_version': metadata.get('db_version', 0)
                                })
                except:
                    continue
        
        # 按时间降序排序
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    
    def restore_backup(self, backup_path, target_db_path):
        # 创建临时目录
        temp_dir = os.path.join(self.backup_dir, 'temp_restore')
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # 解压备份文件
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                zipf.extractall(temp_dir)
            
            # 关闭当前数据库连接
            if os.path.exists(target_db_path):
                # 备份当前数据库
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                emergency_backup = f"{target_db_path}.emergency_{timestamp}.bak"
                shutil.copy2(target_db_path, emergency_backup)
                
                # 替换数据库文件
                for filename in os.listdir(temp_dir):
                    if filename.endswith('.db'):
                        shutil.copy2(os.path.join(temp_dir, filename), target_db_path)
                    elif filename.endswith('-wal'):
                        shutil.copy2(os.path.join(temp_dir, filename), target_db_path + '-wal')
                    elif filename.endswith('-shm'):
                        shutil.copy2(os.path.join(temp_dir, filename), target_db_path + '-shm')
            
            # 清理临时目录
            shutil.rmtree(temp_dir)
            return True, "恢复成功"
        except Exception as e:
            # 清理临时目录
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            return False, str(e)

# 访问线程
class AccessThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, db_path, interval, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.interval = interval
        self._is_running = True
    
    def run(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # 获取启用的URL和代理
            cursor.execute("SELECT id, url FROM urls WHERE enabled=1")
            urls = cursor.fetchall()
            
            cursor.execute("SELECT id, proxy_type, host, port FROM proxies WHERE enabled=1")
            proxies = cursor.fetchall()
            
            if not urls:
                self.finished.emit(False, "没有启用的URL")
                return
            
            total = len(urls) * len(proxies) if proxies else len(urls)
            processed = 0
            
            for url_id, url in urls:
                if not self._is_running:
                    break
                
                if proxies:
                    for proxy_id, proxy_type, host, port in proxies:
                        if not self._is_running:
                            break
                        
                        # 模拟访问
                        success = False
                        status_code = 0
                        response_time = 0
                        
                        try:
                            # 这里应该是实际的访问代码，但根据要求不要求成功
                            # 模拟随机结果
                            import random
                            success = random.choice([True, False])
                            status_code = random.choice([200, 403, 404, 500, 502])
                            response_time = random.uniform(0.1, 5.0)

                            # 在成功访问后更新计数
                            if success:
                                cursor.execute('''
                                UPDATE urls SET 
                                    success_count = success_count + 1,
                                    updated_at = CURRENT_TIMESTAMP 
                                WHERE id=?
                                ''', (url_id,))
                                
                                cursor.execute('''
                                UPDATE proxies SET 
                                    success_count = success_count + 1,
                                    updated_at = CURRENT_TIMESTAMP 
                                WHERE id=?
                                ''', (proxy_id,))
                            else:
                                cursor.execute('''
                                UPDATE urls SET 
                                    failure_count = failure_count + 1,
                                    updated_at = CURRENT_TIMESTAMP 
                                WHERE id=?
                                ''', (url_id,))
                                
                                cursor.execute('''
                                UPDATE proxies SET 
                                    failure_count = failure_count + 1,
                                    updated_at = CURRENT_TIMESTAMP 
                                WHERE id=?
                                ''', (proxy_id,))
                            conn.commit()
                            
                            # 记录日志
                            cursor.execute('''
                            INSERT INTO access_logs (url_id, proxy_id, success, response_time, status_code)
                            VALUES (?, ?, ?, ?, ?)
                            ''', (url_id, proxy_id, success, response_time, status_code))
                            conn.commit()
                            
                            processed += 1
                            self.progress.emit(processed, total, f"通过 {proxy_type}://{host}:{port} 访问 {url}")
                            
                            # 间隔
                            if self.interval > 0:
                                for i in range(self.interval * 10):
                                    if not self._is_running:
                                        break
                                    time.sleep(0.1)
                        except Exception as e:
                            print(f"访问出错: {e}")
                else:
                    # 没有代理直接访问
                    try:
                        # 模拟访问
                        success = random.choice([True, False])
                        status_code = random.choice([200, 403, 404, 500, 502])
                        response_time = random.uniform(0.1, 5.0)
                        
                        # 更新计数
                        if success:
                            cursor.execute('''
                            UPDATE urls SET 
                                success_count = success_count + 1,
                                updated_at = CURRENT_TIMESTAMP 
                            WHERE id=?
                            ''', (url_id,))
                        else:
                            cursor.execute('''
                            UPDATE urls SET 
                                failure_count = failure_count + 1,
                                updated_at = CURRENT_TIMESTAMP 
                            WHERE id=?
                            ''', (url_id,))
                        conn.commit()
                        
                        cursor.execute('''
                        INSERT INTO access_logs (url_id, success, response_time, status_code)
                        VALUES (?, ?, ?, ?)
                        ''', (url_id, success, response_time, status_code))
                        conn.commit()
                        
                        processed += 1
                        self.progress.emit(processed, total, f"直接访问 {url}")
                        
                        # 间隔
                        if self.interval > 0:
                            for i in range(self.interval * 10):
                                if not self._is_running:
                                    break
                                time.sleep(0.1)
                    except Exception as e:
                        print(f"访问出错: {e}")
            
            conn.close()
            self.finished.emit(True, "访问完成" if self._is_running else "访问已停止")
        except Exception as e:
            self.finished.emit(False, str(e))
    
    def stop(self):
        self._is_running = False

    def _get_random_user_agent(self):
        """生成随机User-Agent"""
        user_agents = [
            # Chrome
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            
            # Firefox
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
            
            # Safari
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15",
            
            # Edge
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59"
        ]
        return random.choice(user_agents)

# 恢复数据库对话框
class RestoreDatabaseDialog(QDialog):
    def __init__(self, backup_manager, parent=None):
        super().__init__(parent)
        self.backup_manager = backup_manager
        self.setWindowTitle("恢复数据库")
        self.setMinimumSize(800, 600)
        
        self.layout = QVBoxLayout()
        
        # 筛选控件
        filter_group = QGroupBox("筛选备份")
        filter_layout = QHBoxLayout()
        
        self.type_filter = QComboBox()
        self.type_filter.addItem("所有类型", "")
        self.type_filter.addItem("自动备份", "auto")
        self.type_filter.addItem("手动备份", "manual")
        self.type_filter.addItem("回滚备份", "rollback")
        self.type_filter.currentIndexChanged.connect(self.update_backup_list)
        
        self.from_date = QDateTimeEdit()
        self.from_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.from_date.setDateTime(QDateTime.currentDateTime().addDays(-7))
        self.from_date.dateTimeChanged.connect(self.update_backup_list)
        
        self.to_date = QDateTimeEdit()
        self.to_date.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.to_date.setDateTime(QDateTime.currentDateTime())
        self.to_date.dateTimeChanged.connect(self.update_backup_list)
        
        filter_layout.addWidget(QLabel("备份类型:"))
        filter_layout.addWidget(self.type_filter)
        filter_layout.addWidget(QLabel("从:"))
        filter_layout.addWidget(self.from_date)
        filter_layout.addWidget(QLabel("到:"))
        filter_layout.addWidget(self.to_date)
        
        filter_group.setLayout(filter_layout)
        self.layout.addWidget(filter_group)
        
        # 备份列表表格
        self.backup_table = QTableWidget()
        self.backup_table.setColumnCount(5)
        self.backup_table.setHorizontalHeaderLabels(["备份时间", "类型", "大小", "数据库版本", "操作"])
        self.backup_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.backup_table.verticalHeader().setVisible(False)
        self.backup_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.backup_table.setEditTriggers(QTableWidget.NoEditTriggers)
        
        self.layout.addWidget(self.backup_table)
        
        # 详细信息预览
        self.details_group = QGroupBox("备份详细信息")
        self.details_layout = QVBoxLayout()
        self.details_text = QLabel("选择备份文件查看详细信息")
        self.details_text.setWordWrap(True)
        self.details_layout.addWidget(self.details_text)
        self.details_group.setLayout(self.details_layout)
        self.layout.addWidget(self.details_group)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.button(QDialogButtonBox.Ok).setText("恢复")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        self.layout.addWidget(button_box)
        
        self.setLayout(self.layout)
        
        # 初始化备份列表
        self.update_backup_list()
        
        # 连接信号
        self.backup_table.cellClicked.connect(self.show_backup_details)
    
    def update_backup_list(self):
        backups = self.backup_manager.list_backups()
        
        # 应用筛选
        backup_type = self.type_filter.currentData()
        from_date = self.from_date.dateTime().toString("yyyyMMdd_HHmmss")
        to_date = self.to_date.dateTime().toString("yyyyMMdd_HHmmss")
        
        filtered_backups = []
        for backup in backups:
            if backup_type and backup['type'] != backup_type:
                continue
            if backup['timestamp'] < from_date or backup['timestamp'] > to_date:
                continue
            filtered_backups.append(backup)
        
        # 更新表格
        self.backup_table.setRowCount(len(filtered_backups))
        for row, backup in enumerate(filtered_backups):
            # 格式化时间
            dt = datetime.datetime.strptime(backup['timestamp'], "%Y%m%d_%H%M%S")
            time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            
            # 格式化大小
            size_mb = backup['size'] / (1024 * 1024)
            size_str = f"{size_mb:.2f} MB"
            
            # 类型显示
            type_map = {
                'auto': '自动备份',
                'manual': '手动备份',
                'rollback': '回滚备份'
            }
            type_str = type_map.get(backup['type'], backup['type'])
            
            # 添加表格项
            self.backup_table.setItem(row, 0, QTableWidgetItem(time_str))
            self.backup_table.setItem(row, 1, QTableWidgetItem(type_str))
            self.backup_table.setItem(row, 2, QTableWidgetItem(size_str))
            self.backup_table.setItem(row, 3, QTableWidgetItem(str(backup['db_version'])))
            
            # 操作按钮
            btn = QPushButton("查看详情")
            btn.setProperty('backup_path', backup['path'])
            btn.clicked.connect(lambda _, r=row: self.show_backup_details(r))
            self.backup_table.setCellWidget(row, 4, btn)
    
    def show_backup_details(self, row):
        backup_path = self.backup_table.cellWidget(row, 4).property('backup_path')
        
        try:
            with zipfile.ZipFile(backup_path, 'r') as zipf:
                if 'metadata.json' in zipf.namelist():
                    with zipf.open('metadata.json') as f:
                        metadata = json.load(f)
                        
                        # 获取数据库中的URL范围
                        temp_dir = os.path.join(self.backup_manager.backup_dir, 'temp_preview')
                        os.makedirs(temp_dir, exist_ok=True)
                        zipf.extractall(temp_dir)
                        
                        db_file = None
                        for fname in os.listdir(temp_dir):
                            if fname.endswith('.db'):
                                db_file = os.path.join(temp_dir, fname)
                                break
                        
                        if db_file:
                            conn = sqlite3.connect(db_file)
                            cursor = conn.cursor()
                            
                            # 获取URL数量和日期范围
                            cursor.execute("SELECT COUNT(*) FROM urls")
                            url_count = cursor.fetchone()[0]
                            
                            cursor.execute("SELECT MIN(created_at), MAX(created_at) FROM urls")
                            min_date, max_date = cursor.fetchone()
                            
                            cursor.execute("SELECT COUNT(*) FROM proxies")
                            proxy_count = cursor.fetchone()[0]
                            
                            conn.close()
                            
                            details = (
                                f"备份类型: {metadata.get('backup_type', '未知')}\n"
                                f"备份时间: {datetime.datetime.strptime(metadata['timestamp'], '%Y%m%d_%H%M%S').strftime('%Y-%m-%d %H:%M:%S')}\n"
                                f"数据库版本: {metadata.get('db_version', '未知')}\n"
                                f"文件大小: {metadata.get('size', 0) / (1024 * 1024):.2f} MB\n"
                                f"包含URL数量: {url_count}\n"
                                f"包含代理数量: {proxy_count}\n"
                                f"最早记录: {min_date}\n"
                                f"最新记录: {max_date}"
                            )
                        else:
                            details = "无法提取数据库信息"
                        
                        shutil.rmtree(temp_dir)
                else:
                    details = "备份文件缺少元数据"
        except Exception as e:
            details = f"无法读取备份文件: {str(e)}"
        
        self.details_text.setText(details)
    
    def selected_backup(self):
        selected_rows = self.backup_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        
        row = selected_rows[0].row()
        backup_path = self.backup_table.cellWidget(row, 4).property('backup_path')
        return backup_path

# 用户管理对话框
class UserManagerDialog(QDialog):
    def __init__(self, app_dir, current_user, parent=None):
        super().__init__(parent)
        self.app_dir = app_dir
        self.current_user = current_user
        self.setWindowTitle("用户管理")
        self.setMinimumSize(400, 300)
        
        self.layout = QVBoxLayout()
        
        # 用户列表
        self.user_list = QListWidget()
        self.refresh_user_list()
        self.layout.addWidget(self.user_list)
        
        # 按钮组
        button_layout = QHBoxLayout()
        
        self.add_btn = QPushButton("添加用户")
        self.add_btn.clicked.connect(self.add_user)
        button_layout.addWidget(self.add_btn)
        
        self.delete_btn = QPushButton("删除用户")
        self.delete_btn.clicked.connect(self.delete_user)
        button_layout.addWidget(self.delete_btn)
        
        self.rename_btn = QPushButton("重命名用户")
        self.rename_btn.clicked.connect(self.rename_user)
        button_layout.addWidget(self.rename_btn)
        
        self.switch_btn = QPushButton("切换用户")
        self.switch_btn.clicked.connect(self.switch_user)
        button_layout.addWidget(self.switch_btn)
        
        self.layout.addLayout(button_layout)
        
        # 关闭按钮
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        self.layout.addWidget(close_btn)
        
        self.setLayout(self.layout)
    
    def refresh_user_list(self):
        self.user_list.clear()
        
        # 获取所有用户数据库文件
        user_dbs = []
        for fname in os.listdir(self.app_dir):
            if fname.endswith('.db') and not fname.startswith('.'):
                username = fname[:-3]  # 去掉.db后缀
                user_dbs.append(username)
        
        for username in sorted(user_dbs):
            item = QListWidgetItem(username)
            if username == self.current_user:
                item.setBackground(QColor(200, 255, 200))
            self.user_list.addItem(item)
    
    def add_user(self):
        username, ok = QInputDialog.getText(self, "添加用户", "请输入用户名:")
        if ok and username:
            if not username.isalnum():
                QMessageBox.warning(self, "错误", "用户名只能包含字母和数字")
                return
            
            db_path = os.path.join(self.app_dir, f"{username}.db")
            if os.path.exists(db_path):
                QMessageBox.warning(self, "错误", "用户已存在")
                return
            
            try:
                init_db(db_path)
                self.refresh_user_list()
                QMessageBox.information(self, "成功", f"用户 {username} 已创建")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"创建用户失败: {str(e)}")
    
    def delete_user(self):
        selected = self.user_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "错误", "请选择要删除的用户")
            return
        
        username = selected.text()
        if username == self.current_user:
            QMessageBox.warning(self, "错误", "不能删除当前登录的用户")
            return
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除用户 {username} 吗? 所有数据将永久丢失!", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            db_path = os.path.join(self.app_dir, f"{username}.db")
            try:
                os.remove(db_path)
                
                # 删除备份
                backup_dir = os.path.join(self.app_dir, 'backups', username)
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir)
                
                self.refresh_user_list()
                QMessageBox.information(self, "成功", f"用户 {username} 已删除")
            except Exception as e:
                QMessageBox.critical(self, "错误", f"删除用户失败: {str(e)}")
    
    def rename_user(self):
        selected = self.user_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "错误", "请选择要重命名的用户")
            return
        
        old_username = selected.text()
        new_username, ok = QInputDialog.getText(
            self, "重命名用户", 
            "请输入新用户名:", 
            text=old_username
        )
        
        if ok and new_username and new_username != old_username:
            if not new_username.isalnum():
                QMessageBox.warning(self, "错误", "用户名只能包含字母和数字")
                return
            
            old_db = os.path.join(self.app_dir, f"{old_username}.db")
            new_db = os.path.join(self.app_dir, f"{new_username}.db")
            
            if os.path.exists(new_db):
                QMessageBox.warning(self, "错误", "用户名已存在")
                return
            
            try:
                if old_username == self.current_user:
                    # 如果是当前用户，需要先关闭主窗口的数据库连接
                    parent = self.parent()
                    if isinstance(parent, MainWindow):
                        if not parent.close_database():
                            QMessageBox.critical(self, "错误", "无法关闭当前数据库连接")
                            return
                
                # 尝试重命名3次，每次间隔0.5秒
                max_retries = 3
                for i in range(max_retries):
                    try:
                        os.rename(old_db, new_db)
                        break
                    except PermissionError as e:
                        if i == max_retries - 1:
                            raise
                        time.sleep(0.5)
                
                # 重命名备份目录
                old_backup_dir = os.path.join(self.app_dir, 'backups', old_username)
                new_backup_dir = os.path.join(self.app_dir, 'backups', new_username)
                if os.path.exists(old_backup_dir):
                    os.rename(old_backup_dir, new_backup_dir)
                
                self.refresh_user_list()
                QMessageBox.information(self, "成功", f"用户已从 {old_username} 重命名为 {new_username}")
                
                if old_username == self.current_user:
                    self.current_user = new_username
                    # 如果是当前用户，需要重新打开数据库
                    parent = self.parent()
                    if isinstance(parent, MainWindow):
                        parent.db_path = new_db
                        parent.conn = init_db(new_db)
                        parent.setWindowTitle(f"网址访问量模拟工具 - {new_username}")
            except Exception as e:
                print(f"[DEBUG] 重命名用户失败: {str(e)}")
                QMessageBox.critical(self, "错误", f"重命名用户失败: {str(e)}")

    
    def switch_user(self):
        selected = self.user_list.currentItem()
        if not selected:
            QMessageBox.warning(self, "错误", "请选择要切换的用户")
            return
        
        username = selected.text()
        if username == self.current_user:
            QMessageBox.information(self, "提示", "已经是当前用户")
            return
        
        self.accept()  # 关闭对话框并返回
        self.selected_user = username

# 主窗口
class MainWindow(QMainWindow):
    def __init__(self, app_dir, username):
        super().__init__()
        self.app_dir = app_dir
        self.username = username
        self.db_path = os.path.join(app_dir, f"{username}.db")
        self.settings = QSettings("URLAccessSimulator", "MainWindow")

        # 设置窗口初始大小
        self.setMinimumSize(1000, 800)  # 最小宽度1000px，高度800px
        self.resize(1200, 900)  # 默认初始大小为1200x900

        # 初始化数据库
        self.conn = init_db(self.db_path)
        self.backup_manager = BackupManager(os.path.join(app_dir, 'backups', username))
        
        # 自动备份设置
        self.backup_max_count = 30
        self.load_settings()
        
        # 创建自动备份
        self.create_auto_backup()
        
        # 初始化UI
        self.init_ui()
        
        # 初始化系统托盘
        # self.init_system_tray()
        
        # 访问线程
        self.access_thread = None
        
        # 加载数据
        self.load_urls()
        self.load_proxies()

        # 添加一些默认的代理网站
        if not self.has_proxy_sites():
            self.add_default_proxy_sites()

        # 恢复窗口几何
        self.restore_geometry()


        # 绑定导入导出方法
        self.import_urls_btn = None
        self.export_urls_btn = None
        self.import_proxies_btn = None
        self.export_proxies_btn = None

        # 加载无人值守设置
        self.load_unattended_settings()
        
        # 将设置应用到UI控件
        self.auto_crawl_check.setChecked(self.auto_crawl_enabled)
        self.auto_crawl_interval.setValue(self.auto_crawl_interval_value)
        self.auto_access_check.setChecked(self.auto_access_enabled)
        self.auto_access_interval.setValue(self.auto_access_interval_value)
        self.exec_order_combo.setCurrentIndex(self.execution_order)

    def load_unattended_settings(self):
        """从数据库加载无人值守设置"""
        cursor = self.conn.cursor()
        try:
            # 加载设置
            cursor.execute("SELECT value FROM settings WHERE key='auto_crawl_enabled'")
            self.auto_crawl_enabled = bool(int(cursor.fetchone()[0]))
            
            cursor.execute("SELECT value FROM settings WHERE key='auto_crawl_interval'")
            self.auto_crawl_interval_value = int(cursor.fetchone()[0])
            
            cursor.execute("SELECT value FROM settings WHERE key='auto_access_enabled'")
            self.auto_access_enabled = bool(int(cursor.fetchone()[0]))
            
            cursor.execute("SELECT value FROM settings WHERE key='auto_access_interval'")
            self.auto_access_interval_value = int(cursor.fetchone()[0])
            
            cursor.execute("SELECT value FROM settings WHERE key='execution_order'")
            self.execution_order = int(cursor.fetchone()[0])
        except:
            # 如果设置不存在，使用默认值
            self.auto_crawl_enabled = False
            self.auto_crawl_interval_value = 60
            self.auto_access_enabled = False
            self.auto_access_interval_value = 30
            self.execution_order = 0
    
    def save_unattended_settings(self):
        """保存无人值守设置到数据库"""
        cursor = self.conn.cursor()
        try:
            settings = [
                ('auto_crawl_enabled', str(int(self.auto_crawl_check.isChecked()))),
                ('auto_crawl_interval', str(self.auto_crawl_interval.value())),
                ('auto_access_enabled', str(int(self.auto_access_check.isChecked()))),
                ('auto_access_interval', str(self.auto_access_interval.value())),
                ('execution_order', str(self.exec_order_combo.currentIndex()))
            ]
            
            cursor.executemany(
                'INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)',
                settings
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"保存无人值守设置失败: {str(e)}")
            
    def init_ui(self):
        # 设置窗口标题
        self.setWindowTitle(f"网址访问量模拟工具 - {self.username}")
        # self.setWindowTitle(f"{ProjectInfo.NAME} - {self.username} - {ProjectInfo.VERSION} (Build: {ProjectInfo.BUILD_DATE})")

        # 初始化状态栏
        self.statusBar().showMessage("就绪")

        # 设置窗口图标
        icon_path = os.path.join(self.app_dir, 'icon.ico')
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        
        # 主控件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        
        # 标签页
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        # URL标签页
        self.url_tab = QWidget()
        self.url_layout = QVBoxLayout()
        self.url_tab.setLayout(self.url_layout)
        
        # URL表格
        self.url_table = QTableWidget()
        self.url_table.setColumnCount(5)  # 从3改为5
        self.url_table.setHorizontalHeaderLabels(["启用", "URL", "成功", "失败", "操作"])
        self.url_table.setSortingEnabled(True)
        self.url_table.sortByColumn(2, Qt.DescendingOrder)  # 默认按成功次数降序排列
        self.url_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.url_table.verticalHeader().setVisible(False)
        self.url_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        # URL操作按钮
        url_button_layout = QHBoxLayout()
        
        self.add_url_btn = QPushButton("添加URL")
        self.add_url_btn.clicked.connect(self.add_url)
        url_button_layout.addWidget(self.add_url_btn)
        
        self.delete_url_btn = QPushButton("删除选中")
        self.delete_url_btn.clicked.connect(self.delete_selected_urls)
        url_button_layout.addWidget(self.delete_url_btn)
        
        self.url_search = QLineEdit()
        self.url_search.setPlaceholderText("搜索URL...")
        self.url_search.textChanged.connect(self.load_urls)
        url_button_layout.addWidget(self.url_search)
        
        self.url_layout.addWidget(self.url_table)
        self.url_layout.addLayout(url_button_layout)
        
        # 代理标签页
        self.proxy_tab = QWidget()
        self.proxy_layout = QVBoxLayout()
        self.proxy_tab.setLayout(self.proxy_layout)
        
        # 代理表格
        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(7)  # 从5改为7
        self.proxy_table.setHorizontalHeaderLabels(["启用", "类型", "主机", "端口", "成功", "失败", "操作"])
        self.proxy_table.setSortingEnabled(True)
        self.proxy_table.sortByColumn(4, Qt.DescendingOrder)  # 默认按成功次数降序排列
        self.proxy_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.proxy_table.verticalHeader().setVisible(False)
        self.proxy_table.setSelectionBehavior(QTableWidget.SelectRows)
        
        # 代理操作按钮
        proxy_button_layout = QHBoxLayout()
        
        self.add_proxy_btn = QPushButton("添加代理")
        self.add_proxy_btn.clicked.connect(self.add_proxy)
        proxy_button_layout.addWidget(self.add_proxy_btn)
        
        self.delete_proxy_btn = QPushButton("删除选中")
        self.delete_proxy_btn.clicked.connect(self.delete_selected_proxies)
        proxy_button_layout.addWidget(self.delete_proxy_btn)
        
        self.proxy_search = QLineEdit()
        self.proxy_search.setPlaceholderText("搜索代理...")
        self.proxy_search.textChanged.connect(self.load_proxies)
        proxy_button_layout.addWidget(self.proxy_search)
        
        self.proxy_layout.addWidget(self.proxy_table)
        self.proxy_layout.addLayout(proxy_button_layout)

        # 添加列表管理标签页
        self.list_management_tab = QWidget()
        self.list_management_layout = QVBoxLayout()
        self.list_management_tab.setLayout(self.list_management_layout)
        
        # 添加列表管理功能按钮
        management_button_layout = QHBoxLayout()
        
        self.import_urls_btn = QPushButton("导入URL列表")
        self.import_urls_btn.clicked.connect(self.import_urls)
        management_button_layout.addWidget(self.import_urls_btn)
        
        self.export_urls_btn = QPushButton("导出URL列表")
        self.export_urls_btn.clicked.connect(self.export_urls)
        management_button_layout.addWidget(self.export_urls_btn)
        
        self.import_proxies_btn = QPushButton("导入代理列表")
        self.import_proxies_btn.clicked.connect(self.import_proxies)
        management_button_layout.addWidget(self.import_proxies_btn)
        
        self.export_proxies_btn = QPushButton("导出代理列表")
        self.export_proxies_btn.clicked.connect(self.export_proxies)
        management_button_layout.addWidget(self.export_proxies_btn)
        
        self.list_management_layout.addLayout(management_button_layout)
        
        # 添加格式说明
        format_label = QLabel("支持格式: TXT(每行一个条目), JSON(结构化数据), CSV(逗号分隔)")
        format_label.setStyleSheet("color: gray; font-size: 10px;")
        self.list_management_layout.addWidget(format_label)

        # 添加标签页
        self.tabs.addTab(self.url_tab, "访问地址列表")
        self.tabs.addTab(self.proxy_tab, "代理服务器列表")
        self.tabs.addTab(self.list_management_tab, "列表管理")

        # 添加无人值守标签页
        self.unattended_tab = QWidget()
        self.unattended_layout = QVBoxLayout()
        self.unattended_tab.setLayout(self.unattended_layout)
        
        # 无人值守设置组
        unattended_group = QGroupBox("无人值守设置")
        unattended_form = QFormLayout()
        
        # 自动爬取代理设置
        self.auto_crawl_check = QCheckBox("启用自动爬取代理")
        self.auto_crawl_interval = QSpinBox()
        self.auto_crawl_interval.setRange(1, 24*60)  # 1分钟到24小时
        self.auto_crawl_interval.setValue(60)  # 默认1小时
        self.auto_crawl_interval.setSuffix(" 分钟")
        
        # 自动访问设置
        self.auto_access_check = QCheckBox("启用自动访问")
        self.auto_access_interval = QSpinBox()
        self.auto_access_interval.setRange(1, 24*60)  # 1分钟到24小时
        self.auto_access_interval.setValue(30)  # 默认30分钟
        self.auto_access_interval.setSuffix(" 分钟")
        
        # 执行顺序
        self.exec_order_combo = QComboBox()
        self.exec_order_combo.addItems([
            "先爬取代理后访问",
            "先访问后爬取代理",
            "同时进行"
        ])
        
        # 添加到表单
        unattended_form.addRow(self.auto_crawl_check)
        unattended_form.addRow("爬取间隔:", self.auto_crawl_interval)
        unattended_form.addRow(self.auto_access_check)
        unattended_form.addRow("访问间隔:", self.auto_access_interval)
        unattended_form.addRow("执行顺序:", self.exec_order_combo)
        
        # 控制按钮
        self.start_unattended_btn = QPushButton("开始无人值守")
        self.start_unattended_btn.clicked.connect(self.start_unattended)
        self.stop_unattended_btn = QPushButton("停止无人值守")
        self.stop_unattended_btn.clicked.connect(self.stop_unattended)
        self.stop_unattended_btn.setEnabled(False)
        
        button_layout = QHBoxLayout()
        button_layout.addWidget(self.start_unattended_btn)
        button_layout.addWidget(self.stop_unattended_btn)
        
        unattended_group.setLayout(unattended_form)
        self.unattended_layout.addWidget(unattended_group)
        self.unattended_layout.addLayout(button_layout)
        
        # 状态标签
        self.unattended_status = QLabel("就绪")
        self.unattended_layout.addWidget(self.unattended_status)
        
        # 添加无人值守标签页
        self.tabs.addTab(self.unattended_tab, "无人值守")

        # 控制面板
        control_group = QGroupBox("控制面板")
        control_layout = QGridLayout()
        
        self.start_btn = QPushButton("开始访问")
        self.start_btn.clicked.connect(self.start_access)
        control_layout.addWidget(self.start_btn, 0, 0)
        
        self.stop_btn = QPushButton("停止")
        self.stop_btn.clicked.connect(self.stop_access)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn, 0, 1)
        
        self.interval_label = QLabel("间隔(秒):")
        control_layout.addWidget(self.interval_label, 1, 0)
        
        self.interval_spin = QSpinBox()
        self.interval_spin.setMinimum(0)
        self.interval_spin.setMaximum(3600)
        self.interval_spin.setValue(5)
        control_layout.addWidget(self.interval_spin, 1, 1)
        
        self.status_label = QLabel("就绪")
        control_layout.addWidget(self.status_label, 2, 0, 1, 2)

        # 添加进度条
        self.progress_bar = QProgressBar()
        control_layout.addWidget(self.progress_bar, 3, 0, 1, 2)  # 添加到第4行，跨2列

        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)

        # 代理网站爬取面板
        proxy_crawl_group = QGroupBox("代理服务器爬取")
        proxy_crawl_layout = QGridLayout()

        # 代理网站列表表格
        self.proxy_site_table = QTableWidget()
        self.proxy_site_table.setColumnCount(3)
        self.proxy_site_table.setHorizontalHeaderLabels(["启用", "代理网站URL", "操作"])
        self.proxy_site_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.proxy_site_table.verticalHeader().setVisible(False)
        self.proxy_site_table.setSelectionBehavior(QTableWidget.SelectRows)

        # 代理网站操作按钮
        proxy_site_button_layout = QHBoxLayout()

        self.add_proxy_site_btn = QPushButton("添加代理网站")
        self.add_proxy_site_btn.clicked.connect(self.add_proxy_site)
        proxy_site_button_layout.addWidget(self.add_proxy_site_btn)

        self.delete_proxy_site_btn = QPushButton("删除选中")
        self.delete_proxy_site_btn.clicked.connect(self.delete_selected_proxy_sites)
        proxy_site_button_layout.addWidget(self.delete_proxy_site_btn)

        self.crawl_proxies_btn = QPushButton("爬取代理")
        self.crawl_proxies_btn.clicked.connect(self.crawl_proxies_from_sites)
        proxy_site_button_layout.addWidget(self.crawl_proxies_btn)

        self.crawl_progress = QProgressBar()
        self.crawl_progress.setVisible(False)
        proxy_site_button_layout.addWidget(self.crawl_progress)        

        proxy_crawl_layout.addWidget(self.proxy_site_table, 0, 0, 1, 2)
        proxy_crawl_layout.addLayout(proxy_site_button_layout, 1, 0, 1, 2)

        proxy_crawl_group.setLayout(proxy_crawl_layout)
        main_layout.addWidget(proxy_crawl_group)

        # 加载代理网站列表
        self.load_proxy_sites()

        # 菜单栏
        self.init_menu_bar()
    
    def init_menu_bar(self):
        menubar = self.menuBar()
        
        # 文件菜单
        file_menu = menubar.addMenu("文件")
        
        backup_action = QAction("手动备份", self)
        backup_action.triggered.connect(self.create_manual_backup)
        file_menu.addAction(backup_action)
        
        restore_action = QAction("恢复数据库", self)
        restore_action.triggered.connect(self.show_restore_dialog)
        file_menu.addAction(restore_action)
        
        user_action = QAction("用户管理", self)
        user_action.triggered.connect(self.show_user_manager)
        file_menu.addAction(user_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_application)
        file_menu.addAction(exit_action)

        # 统计菜单
        stats_menu = menubar.addMenu("统计")
        
        reset_url_stats = QAction("重置URL统计", self)
        reset_url_stats.triggered.connect(self.reset_url_stats)
        stats_menu.addAction(reset_url_stats)
        
        reset_proxy_stats = QAction("重置代理统计", self)
        reset_proxy_stats.triggered.connect(self.reset_proxy_stats)
        stats_menu.addAction(reset_proxy_stats)
    
        reset_proxy_site_stats = QAction("重置代理网站统计", self)
        reset_proxy_site_stats.triggered.connect(self.reset_proxy_site_stats)
        stats_menu.addAction(reset_proxy_site_stats)

        # 设置菜单
        settings_menu = menubar.addMenu("设置")
        
        backup_settings_action = QAction("备份设置", self)
        backup_settings_action.triggered.connect(self.show_backup_settings)
        settings_menu.addAction(backup_settings_action)
    
    def init_system_tray(self):
        #if not QSystemTrayIcon.isSystemTrayAvailable():
        #    return
        #
        #self.tray_icon = QSystemTrayIcon(self)
        
        icon_path = os.path.join(self.app_dir, 'icon.ico')
        if os.path.exists(icon_path):
            self.tray_icon.setIcon(QIcon(icon_path))
        
        tray_menu = QMenu()
        
        show_action = QAction("显示窗口", self)
        show_action.triggered.connect(self.show_normal)
        tray_menu.addAction(show_action)
        
        hide_action = QAction("隐藏窗口", self)
        hide_action.triggered.connect(self.hide)
        tray_menu.addAction(hide_action)
        
        exit_action = QAction("退出", self)
        exit_action.triggered.connect(self.quit_application)
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.show()
        
        # 点击托盘图标显示/隐藏窗口
        self.tray_icon.activated.connect(self.toggle_window_visibility)

    def close_database(self):
        """关闭当前数据库连接"""
        if hasattr(self, 'conn') and self.conn:
            try:
                self.conn.close()
                self.conn = None
                return True
            except:
                return False
        return True

    def quit_application(self):
        # 保存窗口状态
        self.save_geometry()
        
        # 停止访问线程
        if self.access_thread and self.access_thread.isRunning():
            self.access_thread.stop()
            self.access_thread.wait()
        
        # 关闭数据库连接
        if self.conn:
            self.conn.close()
        
        # 退出应用程序
        QApplication.quit()

    def import_urls(self):
        """导入URL列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入URL列表", "", 
            "支持的文件类型 (*.txt *.json *.csv);;文本文件 (*.txt);;JSON文件 (*.json);;CSV文件 (*.csv)"
        )
        
        if not file_path:
            self.statusBar().showMessage("导入已取消", 2000)
            return
        
        try:
            urls = []
            if file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        urls = [item['url'] if isinstance(item, dict) else item for item in data]
            elif file_path.endswith('.csv'):
                import csv
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row and row[0].strip():
                            urls.append(row[0].strip())
            else:  # 默认按文本文件处理
                with open(file_path, 'r', encoding='utf-8') as f:
                    urls = [line.strip() for line in f if line.strip()]
            
            if not urls:
                QMessageBox.warning(self, "警告", "文件中没有有效的URL")
                return
            
            cursor = self.conn.cursor()
            added = 0
            for url in urls:
                try:
                    if not url.startswith(('http://', 'https://')):
                        url = 'http://' + url
                    
                    # 检查是否已存在
                    cursor.execute("SELECT 1 FROM urls WHERE url=?", (url,))
                    if not cursor.fetchone():
                        cursor.execute("INSERT INTO urls (url) VALUES (?)", (url,))
                        added += 1
                except:
                    continue
            
            self.conn.commit()
            self.load_urls()
            self.statusBar().showMessage(f"成功导入 {added}/{len(urls)} 个URL", 5000)
        except Exception as e:
            self.statusBar().showMessage(f"导入URL失败: {str(e)}", 5000)
            QMessageBox.critical(self, "错误", f"导入URL失败: {str(e)}")  # 保留关键错误弹窗

    def export_urls(self):
        """导出URL列表"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出URL列表", "urls_export", 
            "支持的文件类型 (*.txt *.json *.csv);;文本文件 (*.txt);;JSON文件 (*.json);;CSV文件 (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT url FROM urls ORDER BY created_at")
            urls = [row[0] for row in cursor.fetchall()]
            
            if not urls:
                QMessageBox.warning(self, "警告", "没有URL可以导出")
                return
            
            if file_path.endswith('.json'):
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(urls, f, indent=2, ensure_ascii=False)
            elif file_path.endswith('.csv'):
                import csv
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    for url in urls:
                        writer.writerow([url])
            else:  # 默认按文本文件处理
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(urls))
            
            QMessageBox.information(self, "成功", f"成功导出 {len(urls)} 个URL")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出URL失败: {str(e)}")

    def import_proxies(self):
        """导入代理列表"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入代理列表", "", 
            "支持的文件类型 (*.txt *.json *.csv);;文本文件 (*.txt);;JSON文件 (*.json);;CSV文件 (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            proxies = []
            if file_path.endswith('.json'):
                with open(file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                # 处理JSON格式的代理
                                proxy_type = item.get('type', 'http').lower()
                                host_port_str = item.get('host', '')
                                
                                # 处理带协议前缀的情况
                                if '://' in host_port_str:
                                    parts = host_port_str.split('://')
                                    proxy_type = parts[0].lower()
                                    host_port_str = parts[1]
                                
                                host, port = self._parse_host_port(host_port_str)
                                if host and port:
                                    proxies.append((proxy_type, host, port))
            elif file_path.endswith('.csv'):
                import csv
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if len(row) >= 2:
                            # 处理CSV格式的代理
                            proxy_type = (row[0].strip().lower() if len(row) > 2 else 'http')
                            host_port_str = row[1].strip()
                            
                            # 处理带协议前缀的情况
                            if '://' in host_port_str:
                                parts = host_port_str.split('://')
                                proxy_type = parts[0].lower()
                                host_port_str = parts[1]
                            
                            host, port = self._parse_host_port(host_port_str)
                            if host and port:
                                proxies.append((proxy_type, host, port))
            else:  # 默认按文本文件处理
                with open(file_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        
                        # 处理文本格式的代理
                        proxy_type = 'http'  # 默认类型
                        host_port_str = line
                        
                        # 处理带协议前缀的情况
                        if '://' in line:
                            parts = line.split('://')
                            proxy_type = parts[0].lower()
                            host_port_str = parts[1]
                        
                        host, port = self._parse_host_port(host_port_str)
                        if host and port:
                            proxies.append((proxy_type, host, port))
            
            if not proxies:
                QMessageBox.warning(self, "警告", "文件中没有有效的代理")
                return
            
            cursor = self.conn.cursor()
            added = 0
            for proxy_type, host, port in proxies:
                try:
                    port = int(port)
                    if not (1 <= port <= 65535):
                        continue
                    
                    # 检查是否已存在
                    cursor.execute(
                        "SELECT 1 FROM proxies WHERE proxy_type=? AND host=? AND port=?", 
                        (proxy_type, host, port)
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO proxies (proxy_type, host, port) VALUES (?, ?, ?)", 
                            (proxy_type, host, port)
                        )
                        added += 1
                except:
                    continue
            
            self.conn.commit()
            self.load_proxies()
            QMessageBox.information(self, "成功", f"成功导入 {added}/{len(proxies)} 个代理")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导入代理失败: {str(e)}")

    def _parse_host_port(self, host_port_str):
        """解析主机和端口字符串"""
        # 处理IPv6地址
        if host_port_str.startswith('['):
            # IPv6格式 [address]:port
            end_bracket = host_port_str.find(']')
            if end_bracket != -1:
                host = host_port_str[1:end_bracket]
                port_part = host_port_str[end_bracket+1:]
                if port_part.startswith(':'):
                    port = port_part[1:]
                else:
                    port = None
            else:
                host = port = None
        else:
            # IPv4格式或域名
            parts = host_port_str.split(':')
            if len(parts) == 2:
                host, port = parts
            elif len(parts) > 2:
                # 可能是IPv6地址没有用[]括起来
                host = ':'.join(parts[:-1])
                port = parts[-1]
            else:
                host = parts[0]
                port = None
        
        # 验证主机和端口
        if not host:
            return None, None
        
        if port:
            try:
                port = int(port)
                if not (1 <= port <= 65535):
                    return None, None
            except ValueError:
                return None, None
        else:
            # 如果没有指定端口，使用协议默认端口
            return host, None
        
        return host, port


    def export_proxies(self):
        """导出代理列表"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出代理列表", "proxies_export", 
            "支持的文件类型 (*.txt *.json *.csv);;文本文件 (*.txt);;JSON文件 (*.json);;CSV文件 (*.csv)"
        )
        
        if not file_path:
            return
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT proxy_type, host, port FROM proxies ORDER BY created_at")
            proxies = cursor.fetchall()
            
            if not proxies:
                QMessageBox.warning(self, "警告", "没有代理可以导出")
                return
            
            if file_path.endswith('.json'):
                data = [
                    {'type': p[0], 'host': p[1], 'port': p[2]}
                    for p in proxies
                ]
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            elif file_path.endswith('.csv'):
                import csv
                with open(file_path, 'w', encoding='utf-8', newline='') as f:
                    writer = csv.writer(f)
                    for p in proxies:
                        writer.writerow([p[0], p[1], p[2]])
            else:  # 默认按文本文件处理
                with open(file_path, 'w', encoding='utf-8') as f:
                    for p in proxies:
                        f.write(f"{p[0]}:{p[1]}:{p[2]}\n")
            
            QMessageBox.information(self, "成功", f"成功导出 {len(proxies)} 个代理")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"导出代理失败: {str(e)}")


    def toggle_window_visibility(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_normal()
    
    def show_normal(self):
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowMinimized | Qt.WindowActive)
        self.activateWindow()
    
    def load_urls(self):
        search_text = self.url_search.text().strip()
        
        cursor = self.conn.cursor()
        
        if search_text:
            # 支持中文、拼音首字母搜索
            pinyin_search = ''.join([s[0] for s in lazy_pinyin(search_text)])
            
            cursor.execute('''
            SELECT id, url, enabled, success_count, failure_count FROM urls 
            WHERE url LIKE ? OR url LIKE ? OR url LIKE ?
            ORDER BY created_at DESC
            ''', (f'%{search_text}%', f'%{pinyin_search}%', f'%{search_text.lower()}%'))
        else:
            cursor.execute('SELECT id, url, enabled, success_count, failure_count FROM urls ORDER BY created_at DESC')
        
        urls = cursor.fetchall()
        
        self.url_table.setRowCount(len(urls))
        for row, (url_id, url, enabled, success_count, failure_count) in enumerate(urls):
            # 启用复选框
            enabled_item = QTableWidgetItem()
            enabled_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            enabled_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
            self.url_table.setItem(row, 0, enabled_item)
            
            # URL
            url_item = QTableWidgetItem(url)
            url_item.setData(Qt.UserRole, url_id)  # 保存ID
            self.url_table.setItem(row, 1, url_item)
            
            # 成功次数
            success_item = QTableWidgetItem(str(success_count))
            success_item.setTextAlignment(Qt.AlignCenter)
            self.url_table.setItem(row, 2, success_item)
            
            # 失败次数
            failure_item = QTableWidgetItem(str(failure_count))
            failure_item.setTextAlignment(Qt.AlignCenter)
            self.url_table.setItem(row, 3, failure_item)
            
            # 操作按钮
            btn = QPushButton("编辑")
            btn.clicked.connect(lambda _, r=row: self.edit_url(r))
            self.url_table.setCellWidget(row, 4, btn)
        
        # 连接复选框状态改变信号
        self.url_table.itemChanged.connect(self.url_checkbox_changed)

    
    def load_proxies(self):
        search_text = self.proxy_search.text().strip()
        
        cursor = self.conn.cursor()
        
        if search_text:
            # 支持中文、拼音首字母搜索
            pinyin_search = ''.join([s[0] for s in lazy_pinyin(search_text)])
            
            cursor.execute('''
            SELECT id, proxy_type, host, port, enabled, success_count, failure_count FROM proxies 
            WHERE host LIKE ? OR host LIKE ? OR host LIKE ? OR port LIKE ?
            ORDER BY created_at DESC
            ''', (f'%{search_text}%', f'%{pinyin_search}%', f'%{search_text.lower()}%', f'%{search_text}%'))
        else:
            cursor.execute('SELECT id, proxy_type, host, port, enabled, success_count, failure_count FROM proxies ORDER BY created_at DESC')
        
        proxies = cursor.fetchall()
        
        self.proxy_table.setRowCount(len(proxies))
        for row, (proxy_id, proxy_type, host, port, enabled, success_count, failure_count) in enumerate(proxies):
            # 启用复选框
            enabled_item = QTableWidgetItem()
            enabled_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            enabled_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
            self.proxy_table.setItem(row, 0, enabled_item)
            
            # 代理类型
            type_item = QTableWidgetItem(proxy_type)
            type_item.setData(Qt.UserRole, proxy_id)  # 保存ID
            self.proxy_table.setItem(row, 1, type_item)
            
            # 主机
            host_item = QTableWidgetItem(host)
            self.proxy_table.setItem(row, 2, host_item)
            
            # 端口
            port_item = QTableWidgetItem(str(port))
            self.proxy_table.setItem(row, 3, port_item)
            
            # 成功次数
            success_item = QTableWidgetItem(str(success_count))
            success_item.setTextAlignment(Qt.AlignCenter)
            self.proxy_table.setItem(row, 4, success_item)
            
            # 失败次数
            failure_item = QTableWidgetItem(str(failure_count))
            failure_item.setTextAlignment(Qt.AlignCenter)
            self.proxy_table.setItem(row, 5, failure_item)
            
            # 操作按钮
            btn = QPushButton("编辑")
            btn.clicked.connect(lambda _, r=row: self.edit_proxy(r))
            self.proxy_table.setCellWidget(row, 6, btn)
        
        # 连接复选框状态改变信号
        self.proxy_table.itemChanged.connect(self.proxy_checkbox_changed)

    
    def add_url(self):
        url, ok = QInputDialog.getText(self, "添加URL", "请输入URL:")
        if ok and url:
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            
            cursor = self.conn.cursor()
            try:
                cursor.execute('INSERT INTO urls (url) VALUES (?)', (url,))
                self.conn.commit()
                self.load_urls()
                self.statusBar().showMessage(f"URL已添加: {url}", 3000)
            except sqlite3.Error as e:
                self.statusBar().showMessage(f"添加URL失败: {str(e)}", 5000)
                QMessageBox.critical(self, "错误", f"添加URL失败: {str(e)}")  # 保留关键错误弹窗
    
    def edit_url(self, row):
        url_id = self.url_table.item(row, 1).data(Qt.UserRole)
        old_url = self.url_table.item(row, 1).text()
        
        new_url, ok = QInputDialog.getText(
            self, "编辑URL", 
            "请输入新的URL:", 
            text=old_url
        )
        
        if ok and new_url and new_url != old_url:
            if not new_url.startswith(('http://', 'https://')):
                new_url = 'http://' + new_url
            
            cursor = self.conn.cursor()
            try:
                cursor.execute(
                    'UPDATE urls SET url=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', 
                    (new_url, url_id)
                )
                self.conn.commit()
                self.load_urls()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"更新URL失败: {str(e)}")
    
    def delete_selected_urls(self):
        selected_rows = set(index.row() for index in self.url_table.selectionModel().selectedRows())
        if not selected_rows:
            self.statusBar().showMessage("请选择要删除的URL", 3000)
            return
        
        # 直接删除，不再需要确认对话框
        cursor = self.conn.cursor()
        try:
            for row in sorted(selected_rows, reverse=True):
                url_id = self.url_table.item(row, 1).data(Qt.UserRole)
                cursor.execute('DELETE FROM urls WHERE id=?', (url_id,))
            
            self.conn.commit()
            self.load_urls()
            self.statusBar().showMessage(f"已删除 {len(selected_rows)} 个URL", 3000)
        except sqlite3.Error as e:
            self.statusBar().showMessage(f"删除URL失败: {str(e)}", 5000)
            QMessageBox.critical(self, "错误", f"删除URL失败: {str(e)}")  # 保留关键错误弹窗
    
    def url_checkbox_changed(self, item):
        if item.column() != 0:  # 只处理第一列的复选框
            return
        
        row = item.row()
        # 添加防御性检查
        url_item = self.url_table.item(row, 1)
        if not url_item:  # 如果没有找到URL项，直接返回
            return
            
        url_id = url_item.data(Qt.UserRole)
        enabled = item.checkState() == Qt.Checked
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'UPDATE urls SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', 
                (enabled, url_id)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "错误", f"更新URL状态失败: {str(e)}")
            # 恢复原状态
            self.url_table.blockSignals(True)
            item.setCheckState(Qt.Unchecked if enabled else Qt.Checked)
            self.url_table.blockSignals(False)

    
    def add_proxy(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("添加代理")
        layout = QVBoxLayout()
        
        # 代理类型
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("代理类型:"))
        type_combo = QComboBox()
        type_combo.addItems(["http", "https", "socks5"])
        type_layout.addWidget(type_combo)
        layout.addLayout(type_layout)
        
        # 主机
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("主机:"))
        host_edit = QLineEdit()
        host_edit.setPlaceholderText("例如: 127.0.0.1 或 proxy.example.com")
        host_layout.addWidget(host_edit)
        layout.addLayout(host_layout)
        
        # 端口
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("端口:"))
        port_edit = QLineEdit()
        port_edit.setPlaceholderText("例如: 8080")
        port_layout.addWidget(port_edit)
        layout.addLayout(port_layout)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            proxy_type = type_combo.currentText()
            host = host_edit.text().strip()
            port = port_edit.text().strip()
            
            if not host or not port:
                QMessageBox.warning(self, "错误", "主机和端口不能为空")
                return
            
            try:
                port = int(port)
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "错误", "端口必须是1-65535之间的整数")
                return
            
            cursor = self.conn.cursor()
            try:
                cursor.execute(
                    'INSERT INTO proxies (proxy_type, host, port) VALUES (?, ?, ?)', 
                    (proxy_type, host, port)
                )
                self.conn.commit()
                self.load_proxies()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"添加代理失败: {str(e)}")
    
    def edit_proxy(self, row):
        proxy_id = self.proxy_table.item(row, 1).data(Qt.UserRole)
        old_type = self.proxy_table.item(row, 1).text()
        old_host = self.proxy_table.item(row, 2).text()
        old_port = self.proxy_table.item(row, 3).text()
        
        dialog = QDialog(self)
        dialog.setWindowTitle("编辑代理")
        layout = QVBoxLayout()
        
        # 代理类型
        type_layout = QHBoxLayout()
        type_layout.addWidget(QLabel("代理类型:"))
        type_combo = QComboBox()
        type_combo.addItems(["http", "https", "socks5"])
        type_combo.setCurrentText(old_type)
        type_layout.addWidget(type_combo)
        layout.addLayout(type_layout)
        
        # 主机
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("主机:"))
        host_edit = QLineEdit(old_host)
        host_layout.addWidget(host_edit)
        layout.addLayout(host_layout)
        
        # 端口
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("端口:"))
        port_edit = QLineEdit(old_port)
        port_layout.addWidget(port_edit)
        layout.addLayout(port_layout)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            proxy_type = type_combo.currentText()
            host = host_edit.text().strip()
            port = port_edit.text().strip()
            
            if not host or not port:
                QMessageBox.warning(self, "错误", "主机和端口不能为空")
                return
            
            try:
                port = int(port)
                if not (1 <= port <= 65535):
                    raise ValueError
            except ValueError:
                QMessageBox.warning(self, "错误", "端口必须是1-65535之间的整数")
                return
            
            cursor = self.conn.cursor()
            try:
                cursor.execute(
                    'UPDATE proxies SET proxy_type=?, host=?, port=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', 
                    (proxy_type, host, port, proxy_id)
                )
                self.conn.commit()
                self.load_proxies()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"更新代理失败: {str(e)}")
    
    def delete_selected_proxies(self):
        selected_rows = set(index.row() for index in self.proxy_table.selectionModel().selectedRows())
        if not selected_rows:
            QMessageBox.warning(self, "警告", "请选择要删除的代理")
            return
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除选中的 {len(selected_rows)} 个代理吗?", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            cursor = self.conn.cursor()
            try:
                for row in sorted(selected_rows, reverse=True):
                    proxy_id = self.proxy_table.item(row, 1).data(Qt.UserRole)
                    cursor.execute('DELETE FROM proxies WHERE id=?', (proxy_id,))
                
                self.conn.commit()
                self.load_proxies()
                QMessageBox.information(self, "成功", "代理已删除")
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"删除代理失败: {str(e)}")
    
    def proxy_checkbox_changed(self, item):
        if item.column() != 0:  # 只处理第一列的复选框
            return
        
        row = item.row()
        # 添加防御性检查
        type_item = self.proxy_table.item(row, 1)
        if not type_item:  # 如果没有找到类型项，直接返回
            return
            
        proxy_id = type_item.data(Qt.UserRole)
        enabled = item.checkState() == Qt.Checked
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'UPDATE proxies SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', 
                (enabled, proxy_id)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "错误", f"更新代理状态失败: {str(e)}")
            # 恢复原状态
            self.proxy_table.blockSignals(True)
            item.setCheckState(Qt.Unchecked if enabled else Qt.Checked)
            self.proxy_table.blockSignals(False)

    
    def start_access(self):
        if self.access_thread and self.access_thread.isRunning():
            return
        
        interval = self.interval_spin.value()
        self.access_thread = AccessThread(self.db_path, interval)
        
        self.access_thread.progress.connect(self.update_progress)
        self.access_thread.finished.connect(self.access_finished)
        
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.status_label.setText("正在访问...")

        # 初始化进度条
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(100)  # 初始设置为100，实际最大值会在update_progress中更新

        self.access_thread.start()
    
    def stop_access(self):
        if self.access_thread and self.access_thread.isRunning():
            self.access_thread.stop()
            self.status_label.setText("正在停止...")
    
    def update_progress(self, current, total, message):
        progress = f"{current}/{total}" if total > 0 else "进行中"
        self.status_label.setText(f"{progress} - {message}")
        
        # 更新进度条
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        else:
            # 如果不知道总数，使用不确定模式
            self.progress_bar.setMaximum(0)

    
    def access_finished(self, success, message):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        status_text = f"{'完成' if success else '错误'}: {message}"
        self.status_label.setText(status_text)
        self.statusBar().showMessage(status_text, 5000)
        
        # 重置进度条
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(100 if success else 0)
        
        # 延迟一段时间后恢复"就绪"状态
        QTimer.singleShot(3000, lambda: self.status_label.setText("就绪"))

    
    def create_auto_backup(self):
        success, result = self.backup_manager.create_backup(self.db_path, 'auto')
        if not success:
            print(f"自动备份失败: {result}")
    
    def create_manual_backup(self):
        success, result = self.backup_manager.create_backup(self.db_path, 'manual')
        if success:
            QMessageBox.information(self, "成功", f"备份已创建: {os.path.basename(result)}")
        else:
            QMessageBox.critical(self, "错误", f"备份失败: {result}")
    
    def show_restore_dialog(self):
        # 先创建手动备份
        success, result = self.backup_manager.create_backup(self.db_path, 'rollback')
        if not success:
            QMessageBox.critical(self, "错误", f"无法创建回滚备份: {result}")
            return
        
        dialog = RestoreDatabaseDialog(self.backup_manager, self)
        if dialog.exec_() == QDialog.Accepted:
            backup_path = dialog.selected_backup()
            if backup_path:
                reply = QMessageBox.question(
                    self, "确认恢复", 
                    "确定要恢复此备份吗? 当前数据将被覆盖!", 
                    QMessageBox.Yes | QMessageBox.No
                )
                
                if reply == QDialog.Yes:
                    success, message = self.backup_manager.restore_backup(backup_path, self.db_path)
                    if success:
                        QMessageBox.information(self, "成功", "数据库已恢复")
                        
                        # 重新初始化数据库连接
                        if self.conn:
                            self.conn.close()
                        self.conn = init_db(self.db_path)
                        
                        # 刷新界面数据
                        self.load_urls()
                        self.load_proxies()
                    else:
                        QMessageBox.critical(self, "错误", f"恢复失败: {message}")
    
    def show_user_manager(self):
        dialog = UserManagerDialog(self.app_dir, self.username, self)
        if dialog.exec_() == QDialog.Accepted:
            if hasattr(dialog, 'selected_user'):
                # 切换到新用户
                self.switch_user(dialog.selected_user)
    
    def switch_user(self, new_username):
        # 保存当前窗口状态
        self.save_geometry()
        
        # 关闭当前连接
        if self.conn:
            self.conn.close()
        
        # 停止访问线程
        if self.access_thread and self.access_thread.isRunning():
            self.access_thread.stop()
            self.access_thread.wait()
        
        # 创建新窗口
        new_window = MainWindow(self.app_dir, new_username)
        new_window.show()
        
        # 关闭当前窗口
        self.close()
    
    def show_backup_settings(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("备份设置")
        layout = QVBoxLayout()
        
        # 最大备份数量
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("最大备份数量:"))
        count_spin = QSpinBox()
        count_spin.setMinimum(1)
        count_spin.setMaximum(1000)
        count_spin.setValue(self.backup_max_count)
        count_layout.addWidget(count_spin)
        layout.addLayout(count_layout)
        
        # 按钮
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(dialog.accept)
        button_box.rejected.connect(dialog.reject)
        layout.addWidget(button_box)
        
        dialog.setLayout(layout)
        
        if dialog.exec_() == QDialog.Accepted:
            self.backup_max_count = count_spin.value()
            self.save_settings()
            QMessageBox.information(self, "成功", "设置已保存")
    
    def load_settings(self):
        # 从数据库加载设置
        cursor = self.conn.cursor()
        try:
            cursor.execute("SELECT value FROM settings WHERE key='backup_max_count'")
            result = cursor.fetchone()
            if result:
                self.backup_max_count = int(result[0])
        except sqlite3.Error:
            pass
        
        # 从QSettings加载窗口状态
        self.settings.beginGroup("MainWindow")
        self.backup_max_count = self.settings.value("backup_max_count", self.backup_max_count, type=int)
        self.settings.endGroup()
    
    def save_settings(self):
        # 保存到数据库
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", 
                ('backup_max_count', str(self.backup_max_count))
            )
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"保存设置失败: {str(e)}")
        
        # 保存到QSettings
        self.settings.beginGroup("MainWindow")
        self.settings.setValue("backup_max_count", self.backup_max_count)
        self.settings.endGroup()
    
    def restore_geometry(self):
        self.settings.beginGroup("MainWindow")
        geometry = self.settings.value("geometry")
        state = self.settings.value("windowState")
        if geometry:
            self.restoreGeometry(geometry)
        if state:
            self.restoreState(state)
        self.settings.endGroup()
    
    def save_geometry(self):
        self.settings.beginGroup("MainWindow")
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("windowState", self.saveState())
        self.settings.endGroup()
    
    def closeEvent(self, event):
        # 停止无人值守模式
        if hasattr(self, 'stop_unattended'):
            self.stop_unattended()
    
        # 保存窗口状态
        self.save_geometry()

        # 保存无人值守设置
        self.save_unattended_settings()

        # 停止访问线程
        if self.access_thread and self.access_thread.isRunning():
            self.access_thread.stop()
            self.access_thread.wait()
        
        # 关闭数据库连接
        if self.conn:
            self.conn.close()
        
        # 检查是否有点击托盘退出
        #if hasattr(self, 'explicit_quit') and self.explicit_quit:
        #    event.accept()
        #else:
        #    # 隐藏到托盘
        #    if hasattr(self, 'tray_icon') and self.tray_icon.isVisible():
        #        self.hide()
        #        event.ignore()
        #    else:
        #        event.accept()
            
        # 直接退出程序
        event.accept()


    def load_proxy_sites(self):
        """加载代理网站列表"""
        cursor = self.conn.cursor()
        cursor.execute('SELECT id, url, enabled, success_count, failure_count FROM proxy_sites ORDER BY created_at DESC')
        sites = cursor.fetchall()
        
        # 修改列数为5列（原为3列）
        self.proxy_site_table.setColumnCount(5)
        self.proxy_site_table.setHorizontalHeaderLabels(["启用", "代理网站URL", "成功", "失败", "操作"])
        
        self.proxy_site_table.setRowCount(len(sites))
        for row, (site_id, url, enabled, success_count, failure_count) in enumerate(sites):
            # 启用复选框
            enabled_item = QTableWidgetItem()
            enabled_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            enabled_item.setCheckState(Qt.Checked if enabled else Qt.Unchecked)
            self.proxy_site_table.setItem(row, 0, enabled_item)
            
            # URL
            url_item = QTableWidgetItem(url)
            url_item.setData(Qt.UserRole, site_id)  # 保存ID
            self.proxy_site_table.setItem(row, 1, url_item)
            
            # 成功次数
            success_item = QTableWidgetItem(str(success_count))
            success_item.setTextAlignment(Qt.AlignCenter)
            self.proxy_site_table.setItem(row, 2, success_item)
            
            # 失败次数
            failure_item = QTableWidgetItem(str(failure_count))
            failure_item.setTextAlignment(Qt.AlignCenter)
            self.proxy_site_table.setItem(row, 3, failure_item)
            
            # 操作按钮
            btn = QPushButton("编辑")
            btn.clicked.connect(lambda _, r=row: self.edit_proxy_site(r))
            self.proxy_site_table.setCellWidget(row, 4, btn)
        
        # 连接复选框状态改变信号
        self.proxy_site_table.itemChanged.connect(self.proxy_site_checkbox_changed)


    def add_proxy_site(self):
        """添加代理网站"""
        url, ok = QInputDialog.getText(self, "添加代理网站", "请输入代理网站URL:")
        if ok and url:
            if not url.startswith(('http://', 'https://')):
                url = 'http://' + url
            
            cursor = self.conn.cursor()
            try:
                cursor.execute('INSERT INTO proxy_sites (url) VALUES (?)', (url,))
                self.conn.commit()
                self.load_proxy_sites()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"添加代理网站失败: {str(e)}")

    def edit_proxy_site(self, row):
        """编辑代理网站"""
        site_id = self.proxy_site_table.item(row, 1).data(Qt.UserRole)
        old_url = self.proxy_site_table.item(row, 1).text()
        
        new_url, ok = QInputDialog.getText(
            self, "编辑代理网站", 
            "请输入新的代理网站URL:", 
            text=old_url
        )
        
        if ok and new_url and new_url != old_url:
            if not new_url.startswith(('http://', 'https://')):
                new_url = 'http://' + new_url
            
            cursor = self.conn.cursor()
            try:
                cursor.execute(
                    'UPDATE proxy_sites SET url=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', 
                    (new_url, site_id)
                )
                self.conn.commit()
                self.load_proxy_sites()
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"更新代理网站失败: {str(e)}")

    def delete_selected_proxy_sites(self):
        """删除选中的代理网站"""
        selected_rows = set(index.row() for index in self.proxy_site_table.selectionModel().selectedRows())
        if not selected_rows:
            QMessageBox.warning(self, "警告", "请选择要删除的代理网站")
            return
        
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除选中的 {len(selected_rows)} 个代理网站吗?", 
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            cursor = self.conn.cursor()
            try:
                for row in sorted(selected_rows, reverse=True):
                    site_id = self.proxy_site_table.item(row, 1).data(Qt.UserRole)
                    cursor.execute('DELETE FROM proxy_sites WHERE id=?', (site_id,))
                
                self.conn.commit()
                self.load_proxy_sites()
                QMessageBox.information(self, "成功", "代理网站已删除")
            except sqlite3.Error as e:
                QMessageBox.critical(self, "错误", f"删除代理网站失败: {str(e)}")

    def proxy_site_checkbox_changed(self, item):
        """代理网站启用状态改变"""
        if item.column() != 0:  # 只处理第一列的复选框
            return
        
        row = item.row()
        # 添加防御性检查
        url_item = self.proxy_site_table.item(row, 1)
        if not url_item:  # 如果没有找到URL项，直接返回
            return
            
        site_id = url_item.data(Qt.UserRole)
        enabled = item.checkState() == Qt.Checked
        
        cursor = self.conn.cursor()
        try:
            cursor.execute(
                'UPDATE proxy_sites SET enabled=?, updated_at=CURRENT_TIMESTAMP WHERE id=?', 
                (enabled, site_id)
            )
            self.conn.commit()
        except sqlite3.Error as e:
            QMessageBox.critical(self, "错误", f"更新代理网站状态失败: {str(e)}")
            # 恢复原状态
            self.proxy_site_table.blockSignals(True)
            item.setCheckState(Qt.Unchecked if enabled else Qt.Checked)
            self.proxy_site_table.blockSignals(False)

    def crawl_proxies_from_sites(self):
        """从代理网站爬取代理"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT id, url FROM proxy_sites WHERE enabled=1")
        sites = cursor.fetchall()  # 现在获取ID和URL
        
        if not sites:
            self.statusBar().showMessage("没有启用的代理网站", 5000)
            return

        # 显示进度条
        self.crawl_progress.setMaximum(len(sites))
        self.crawl_progress.setValue(0)
        self.crawl_progress.setVisible(True)
        self.crawl_proxies_btn.setEnabled(False)
        
        proxies = []
        failed_sites = []  # 记录失败的网站
        
        for i, (site_id, site) in enumerate(sites, 1):
            self.crawl_progress.setValue(i)
            self.status_label.setText(f"正在爬取: {site}")
            QApplication.processEvents()
        
            try:
                # 随机延迟1-5秒
                time.sleep(random.uniform(1, 5))

                site_proxies = []
                if "free-proxy-list.com" in site or "free-proxy-list.net" in site:
                    site_proxies = self._parse_free_proxy_list(site)
                elif "sslproxies.org" in site:
                    site_proxies = self._parse_ssl_proxies(site)
                elif "us-proxy.org" in site:
                    site_proxies = self._parse_us_proxies(site)
                elif "hidemy.name" in site:
                    site_proxies = self._parse_hidemy_name(site)
                else:
                    site_proxies = self._parse_generic_proxy_site(site)
                
                if site_proxies:
                    proxies.extend(site_proxies)
                    print(f"成功从 {site} 爬取到 {len(site_proxies)} 个代理")
                    # 更新成功计数
                    cursor.execute('''
                    UPDATE proxy_sites SET 
                        success_count = success_count + 1,
                        updated_at = CURRENT_TIMESTAMP 
                    WHERE id=?
                    ''', (site_id,))
                else:
                    failed_sites.append(site)
                    print(f"从 {site} 爬取代理失败，未获取到代理")
                    # 更新失败计数
                    cursor.execute('''
                    UPDATE proxy_sites SET 
                        failure_count = failure_count + 1,
                        updated_at = CURRENT_TIMESTAMP 
                    WHERE id=?
                    ''', (site_id,))
                
                self.conn.commit()
                        
            except Exception as e:
                print(f"从 {site} 爬取代理失败: {str(e)}")
                failed_sites.append(site)
                # 更新失败计数
                cursor.execute('''
                UPDATE proxy_sites SET 
                    failure_count = failure_count + 1,
                    updated_at = CURRENT_TIMESTAMP 
                WHERE id=?
                ''', (site_id,))
                self.conn.commit()
        
        # 隐藏进度条
        self.crawl_progress.setVisible(False)
        self.crawl_proxies_btn.setEnabled(True)
        self.load_proxy_sites()  # 刷新表格显示最新统计数据

        # 显示结果
        if proxies:
            # 去重处理
            unique_proxies = {}
            for proxy in proxies:
                key = (proxy[0].lower(), proxy[1].lower(), proxy[2])  # (type, host, port) 作为唯一键
                unique_proxies[key] = proxy
        
            # 添加到数据库
            added = 0
            cursor = self.conn.cursor()
            for proxy_type, host, port in unique_proxies.values():
                try:
                    # 检查是否已存在
                    cursor.execute(
                        "SELECT 1 FROM proxies WHERE proxy_type=? AND host=? AND port=?", 
                        (proxy_type, host, port)
                    )
                    if not cursor.fetchone():
                        cursor.execute(
                            "INSERT INTO proxies (proxy_type, host, port) VALUES (?, ?, ?)", 
                            (proxy_type, host, port)
                        )
                        added += 1
                except:
                    continue
            
            self.conn.commit()
            self.load_proxies()
            self.status_label.setText(f"成功添加 {added} 个新代理")
            self.statusBar().showMessage(f"成功添加 {added} 个新代理 (爬取到 {len(proxies)} 个，去重后 {len(unique_proxies)} 个)", 5000)
        else:
            self.status_label.setText("没有爬取到有效的代理")
            failed_sites_text = "没有爬取到有效的代理\n\n失败的网站:\n" + "\n".join(failed_sites)
            self.statusBar().showMessage("没有爬取到有效的代理", 5000)

    def _parse_free_proxy_list(self, url):
        """解析 free-proxy-list.com 和 free-proxy-list.net 网站"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': self._get_random_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'DNT': '1',  # Do Not Track
                'Referer': 'https://www.google.com/',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'cross-site',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0'
            }

            # 添加随机延迟
            time.sleep(random.uniform(1, 3))
            
            # 添加重试机制
            for attempt in range(3):  # 最多重试3次
                try:
                    response = requests.get(
                        url,
                        headers=headers,
                        timeout=10,
                        cookies={'session_cookie': str(random.randint(10000, 99999))}
                    )
                    response.raise_for_status()
                    break  # 成功则跳出循环
                except requests.exceptions.RequestException as e:
                    if attempt == 2:  # 最后一次尝试失败
                        print(f"解析 free-proxy-list 失败(第{attempt+1}次尝试): {str(e)}")
                        return []
                    time.sleep(2)  # 等待2秒后重试

            soup = BeautifulSoup(response.text, 'html.parser')
            
            proxies = []
            table = soup.find('table', {'id': 'proxylisttable'})
            if table:
                rows = table.find_all('tr')[1:]  # 跳过表头
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        if cols[6].text.strip().lower() == 'yes':
                            proxy_type = 'https'
                        else:
                            proxy_type = 'http'
                        
                        try:
                            port = int(port)
                            proxies.append((proxy_type, ip, port))
                        except ValueError:
                            continue
            return proxies
        except Exception as e:
            print(f"解析 free-proxy-list 失败: {str(e)}")
            return []

    def _parse_ssl_proxies(self, url):
        """解析 sslproxies.org 网站"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            proxies = []
            table = soup.find('table', {'id': 'proxylisttable'})
            if table:
                rows = table.find_all('tr')[1:]  # 跳过表头
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        proxy_type = 'https'  # 这个网站专门提供SSL代理
                        
                        try:
                            port = int(port)
                            proxies.append((proxy_type, ip, port))
                        except ValueError:
                            continue
            return proxies
        except Exception as e:
            print(f"解析 sslproxies 失败: {str(e)}")
            return []

    def _parse_us_proxies(self, url):
        """解析 us-proxy.org 网站"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            proxies = []
            table = soup.find('table', {'id': 'proxylisttable'})
            if table:
                rows = table.find_all('tr')[1:]  # 跳过表头
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        if cols[6].text.strip().lower() == 'yes':
                            proxy_type = 'https'
                        else:
                            proxy_type = 'http'
                        
                        try:
                            port = int(port)
                            proxies.append((proxy_type, ip, port))
                        except ValueError:
                            continue
            return proxies
        except Exception as e:
            print(f"解析 us-proxies 失败: {str(e)}")
            return []

    def _parse_hidemy_name(self, url):
        """解析 hidemy.name 网站"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            proxies = []
            table = soup.find('table')
            if table:
                rows = table.find_all('tr')[1:]  # 跳过表头
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        ip = cols[0].text.strip()
                        port = cols[1].text.strip()
                        proxy_type = cols[4].text.strip().lower()
                        
                        # 统一代理类型
                        if 'socks' in proxy_type:
                            proxy_type = 'socks5'
                        elif proxy_type not in ['http', 'https']:
                            proxy_type = 'http'
                        
                        try:
                            port = int(port)
                            proxies.append((proxy_type, ip, port))
                        except ValueError:
                            continue
            return proxies
        except Exception as e:
            print(f"解析 hidemy.name 失败: {str(e)}")
            return []

    def _parse_generic_proxy_site(self, url):
        """通用代理网站解析方法"""
        import requests
        from bs4 import BeautifulSoup
        
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            proxies = []
            
            # 尝试查找表格
            for table in soup.find_all('table'):
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        # 尝试提取IP和端口
                        ip = None
                        port = None
                        proxy_type = 'http'  # 默认为http
                        
                        for i, cell in enumerate(cells):
                            text = cell.text.strip()
                            # 检查是否是IP地址
                            if '.' in text and all(part.isdigit() for part in text.split('.')[:3]):
                                ip = text
                            # 检查是否是端口号
                            elif text.isdigit() and 1 <= int(text) <= 65535:
                                port = int(text)
                            # 检查代理类型
                            elif text.lower() in ['http', 'https', 'socks', 'socks4', 'socks5']:
                                proxy_type = 'socks5' if 'socks' in text.lower() else text.lower()
                        
                        if ip and port:
                            proxies.append((proxy_type, ip, port))
            
            return proxies
        except Exception as e:
            print(f"解析通用代理网站 {url} 失败: {str(e)}")
            return []


    def parse_proxies_from_site(self, url):
        """从代理网站解析代理列表
        参数:
            url (str): 要解析的代理网站URL
        返回:
            list: 代理列表，格式为[(proxy_type, host, port), ...]
        """
        try:
            import requests
            from bs4 import BeautifulSoup
            import re
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Connection': 'keep-alive'
            }
            
            # 设置超时和重试
            session = requests.Session()
            session.max_redirects = 3
            session.verify = False  # 忽略SSL证书验证
            
            try:
                response = session.get(url, headers=headers, timeout=15)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                print(f"请求代理网站失败: {str(e)}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            proxies = []
            
            # 常见代理网站的解析规则
            if "free-proxy-list.com" in url or "free-proxy-list.net" in url:
                # 解析 free-proxy-list 格式
                table = soup.find('table', {'id': 'proxylisttable'})
                if table:
                    for row in table.find_all('tr')[1:]:  # 跳过表头
                        cols = [col.text.strip() for col in row.find_all('td')]
                        if len(cols) >= 7:
                            ip = cols[0]
                            port = cols[1]
                            proxy_type = 'https' if cols[6].lower() == 'yes' else 'http'
                            if self._validate_proxy(ip, port):
                                proxies.append((proxy_type, ip, int(port)))
            
            elif "sslproxies.org" in url:
                # 解析 sslproxies 格式
                table = soup.find('table', {'id': 'proxylisttable'})
                if table:
                    for row in table.find_all('tr')[1:]:
                        cols = [col.text.strip() for col in row.find_all('td')]
                        if len(cols) >= 2:
                            ip = cols[0]
                            port = cols[1]
                            if self._validate_proxy(ip, port):
                                proxies.append(('https', ip, int(port)))
            
            elif "us-proxy.org" in url:
                # 解析 us-proxy 格式
                table = soup.find('table', {'id': 'proxylisttable'})
                if table:
                    for row in table.find_all('tr')[1:]:
                        cols = [col.text.strip() for col in row.find_all('td')]
                        if len(cols) >= 7:
                            ip = cols[0]
                            port = cols[1]
                            proxy_type = 'https' if cols[6].lower() == 'yes' else 'http'
                            if self._validate_proxy(ip, port):
                                proxies.append((proxy_type, ip, int(port)))
            
            elif "hidemy.name" in url:
                # 解析 hidemy.name 格式
                table = soup.find('table')
                if table:
                    for row in table.find_all('tr')[1:]:
                        cols = [col.text.strip() for col in row.find_all('td')]
                        if len(cols) >= 5:
                            ip = cols[0]
                            port = cols[1]
                            raw_type = cols[4].lower()
                            proxy_type = 'socks5' if 'socks' in raw_type else raw_type
                            if self._validate_proxy(ip, port):
                                proxies.append((proxy_type, ip, int(port)))
            
            else:
                # 通用解析方法 - 尝试查找表格中的所有IP:Port组合
                ip_port_pattern = re.compile(
                    r'((?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?))'
                    r'[\s:]+'
                    r'(\d{2,5})'
                )
                
                # 在表格中查找
                for table in soup.find_all('table'):
                    for row in table.find_all('tr'):
                        text = row.get_text()
                        matches = ip_port_pattern.findall(text)
                        for ip, port in matches:
                            if self._validate_proxy(ip, port):
                                # 尝试从行文本确定代理类型
                                row_text = row.get_text().lower()
                                if 'socks' in row_text:
                                    proxy_type = 'socks5'
                                elif 'https' in row_text:
                                    proxy_type = 'https'
                                else:
                                    proxy_type = 'http'
                                
                                proxies.append((proxy_type, ip, int(port)))
                
                # 如果没有找到表格，尝试在整个页面中查找
                if not proxies:
                    text = soup.get_text()
                    matches = ip_port_pattern.findall(text)
                    for ip, port in matches:
                        if self._validate_proxy(ip, port):
                            proxies.append(('http', ip, int(port)))
            
            return proxies
        
        except Exception as e:
            print(f"解析代理网站 {url} 时出错: {str(e)}")
            return []

    def _validate_proxy(self, ip, port):
        """验证IP和端口是否有效"""
        try:
            # 验证IP地址
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not part.isdigit():
                    return False
                num = int(part)
                if num < 0 or num > 255:
                    return False
            
            # 验证端口
            port = int(port)
            if port < 1 or port > 65535:
                return False
            
            return True
        except:
            return False



    def has_proxy_sites(self):
        """检查是否有代理网站"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM proxy_sites")
        return cursor.fetchone()[0] > 0

    def add_default_proxy_sites(self):
        """添加默认的代理网站"""
        default_sites = [
            "https://www.free-proxy-list.com/",
            "https://www.sslproxies.org/",
            "https://www.us-proxy.org/",
            "https://free-proxy-list.net/",
            "https://hidemy.name/en/proxy-list/"
        ]
        
        cursor = self.conn.cursor()
        try:
            for url in default_sites:
                cursor.execute("INSERT INTO proxy_sites (url) VALUES (?)", (url,))
            self.conn.commit()
        except sqlite3.Error as e:
            print(f"添加默认代理网站失败: {str(e)}")

    def _get_random_user_agent(self):
        """生成随机User-Agent"""
        user_agents = [
            # Chrome
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            
            # Firefox
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (X11; Linux x86_64; rv:89.0) Gecko/20100101 Firefox/89.0",
            
            # Safari
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1 Safari/605.1.15",
            
            # Edge
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36 Edg/91.0.864.59"
        ]
        return random.choice(user_agents)

    def start_unattended(self):
        """启动无人值守模式"""
        # 保存当前设置
        self.save_unattended_settings()
        
        if not (self.auto_crawl_check.isChecked() or self.auto_access_check.isChecked()):
            self.statusBar().showMessage("请至少启用自动爬取代理或自动访问中的一个选项", 5000)
            return
        
        self.start_unattended_btn.setEnabled(False)
        self.stop_unattended_btn.setEnabled(True)
        self.statusBar().showMessage("无人值守模式已启动")
        self.unattended_status.setText("无人值守模式已启动")
        
        # 初始化计时器
        self.crawl_timer = QTimer()
        self.access_timer = QTimer()
        
        # 设置间隔
        crawl_interval = self.auto_crawl_interval.value() * 60 * 1000  # 转换为毫秒
        access_interval = self.auto_access_interval.value() * 60 * 1000
        
        # 根据执行顺序决定启动顺序
        order = self.exec_order_combo.currentText()
        
        if order == "先爬取代理后访问":
            if self.auto_crawl_check.isChecked():
                self.crawl_proxies_from_sites()
                self.crawl_timer.timeout.connect(self.crawl_proxies_from_sites)
                self.crawl_timer.start(crawl_interval)
            
            if self.auto_access_check.isChecked():
                # 延迟启动访问，确保先完成一次爬取
                QTimer.singleShot(5000, lambda: self.start_access())
                self.access_timer.timeout.connect(self.start_access)
                self.access_timer.start(access_interval)
        
        elif order == "先访问后爬取代理":
            if self.auto_access_check.isChecked():
                self.start_access()
                self.access_timer.timeout.connect(self.start_access)
                self.access_timer.start(access_interval)
            
            if self.auto_crawl_check.isChecked():
                # 延迟启动爬取
                QTimer.singleShot(5000, lambda: self.crawl_proxies_from_sites())
                self.crawl_timer.timeout.connect(self.crawl_proxies_from_sites)
                self.crawl_timer.start(crawl_interval)
        
        else:  # 同时进行
            if self.auto_crawl_check.isChecked():
                self.crawl_proxies_from_sites()
                self.crawl_timer.timeout.connect(self.crawl_proxies_from_sites)
                self.crawl_timer.start(crawl_interval)
            
            if self.auto_access_check.isChecked():
                self.start_access()
                self.access_timer.timeout.connect(self.start_access)
                self.access_timer.start(access_interval)
    def stop_unattended(self):
        """停止无人值守模式"""
        # 保存当前设置
        self.save_unattended_settings()
        
        if hasattr(self, 'crawl_timer') and self.crawl_timer.isActive():
            self.crawl_timer.stop()
        
        if hasattr(self, 'access_timer') and self.access_timer.isActive():
            self.access_timer.stop()
            self.stop_access()  # 停止当前访问
        
        self.start_unattended_btn.setEnabled(True)
        self.stop_unattended_btn.setEnabled(False)
        self.unattended_status.setText("无人值守模式已停止")

    def reset_url_stats(self):
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置所有URL的成功/失败计数吗?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE urls SET success_count=0, failure_count=0")
            self.conn.commit()
            self.load_urls()

    def reset_proxy_stats(self):
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置所有代理的成功/失败计数吗?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE proxies SET success_count=0, failure_count=0")
            self.conn.commit()
            self.load_proxies()

    def reset_proxy_site_stats(self):
        """重置代理网站的成功/失败统计"""
        reply = QMessageBox.question(
            self, "确认重置",
            "确定要重置所有代理网站的成功/失败计数吗?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE proxy_sites SET success_count=0, failure_count=0")
            self.conn.commit()
            self.load_proxy_sites()  # 刷新代理网站列表
            self.statusBar().showMessage("代理网站统计已重置", 3000)


# 应用入口
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle('Fusion')  # 使用Fusion风格，看起来更现代
    
    # 设置应用目录
    app_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    # 创建用户备份目录
    os.makedirs(os.path.join(app_dir, 'backups'), exist_ok=True)

    # 获取所有用户
    user_dbs = []
    for fname in os.listdir(app_dir):
        if fname.endswith('.db') and not fname.startswith('.'):
            username = fname[:-3]  # 去掉.db后缀
            user_dbs.append(username)

    # 如果没有用户，创建默认用户
    if not user_dbs:
        default_user = "default"
        default_db = os.path.join(app_dir, f"{default_user}.db")
        init_db(default_db)
        user_dbs.append(default_user)
        selected_user = default_user
    else:
        # 显示用户选择对话框
        dialog = QDialog()
        dialog.setWindowTitle("选择用户")
        dialog.setMinimumSize(300, 200)
        
        layout = QVBoxLayout()
        layout.addWidget(QLabel("请选择用户:"))
        
        user_list = QListWidget()
        for username in sorted(user_dbs):
            user_list.addItem(username)
        layout.addWidget(user_list)
        
        button_layout = QHBoxLayout()
        
        select_btn = QPushButton("选择")
        select_btn.clicked.connect(dialog.accept)
        button_layout.addWidget(select_btn)
        
        new_btn = QPushButton("新建用户")
        new_btn.clicked.connect(lambda: create_new_user(dialog, user_list))
        button_layout.addWidget(new_btn)
        
        layout.addLayout(button_layout)
        dialog.setLayout(layout)
        
        # 创建新用户函数
        def create_new_user(dialog, user_list):
            username, ok = QInputDialog.getText(dialog, "新建用户", "请输入用户名:")
            if ok and username:
                if not username.isalnum():
                    QMessageBox.warning(dialog, "错误", "用户名只能包含字母和数字")
                    return
                
                db_path = os.path.join(app_dir, f"{username}.db")
                if os.path.exists(db_path):
                    QMessageBox.warning(dialog, "错误", "用户已存在")
                    return
                
                try:
                    init_db(db_path)
                    user_list.addItem(username)
                    QMessageBox.information(dialog, "成功", f"用户 {username} 已创建")
                except Exception as e:
                    QMessageBox.critical(dialog, "错误", f"创建用户失败: {str(e)}")
        
        if dialog.exec_() == QDialog.Accepted:
            selected_item = user_list.currentItem()
            if selected_item:
                selected_user = selected_item.text()
            else:
                selected_user = user_dbs[0]  # 默认选择第一个用户
        else:
            sys.exit(0)  # 用户取消选择，退出程序
    
    # 显示主窗口
    window = MainWindow(app_dir, selected_user)
    window.show()
    
    sys.exit(app.exec_())
