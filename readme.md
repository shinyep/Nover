.\venv\Scripts\activate # 激活虚拟环境
pip install -r requirements.txt # 安装依赖
python manage.py runserver 8001 # 启动django
python manage.py shell  # 进入python shell
pip install requests beautifulsoup4 

python manage.py crawl_novels  # 运行爬虫
python manage.py crawl_book18
python manage.py crawl_xqbj
Django                   # Django框架

novel/
├── novels/
│   ├── migrations/
│   ├── templates/
│   │   └── novels/
│   │       ├── base.html
│   │       ├── index.html
│   │       ├── detail.html
│   │       └── chapter.html
│   ├── __init__.py
│   ├── admin.py       # ← 核心管理配置
│   ├── apps.py
│   ├── models.py
│   ├── urls.py
│   └── views.py
├── mysite/
│   ├── __init__.py
│   ├── settings.py    # ← 关键配置
│   ├── urls.py
│   └── wsgi.py
├── media/             # 用户上传文件
├── static/
│   └── css/
│       └── bootstrap.min.css
└── manage.py
