@echo off
rem 学生报销管家一键启动:双击本文件即可,首次运行自动安装依赖
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto nopython
python -c "import docx, rapidocr_onnxruntime, PIL, tkinterdnd2" >nul 2>nul
if errorlevel 1 goto install
goto run
:install
echo 首次运行,正在安装依赖,需要联网,约 1-2 分钟……
python -m pip install -r requirements.txt
if errorlevel 1 goto failinstall
echo 依赖安装完成。
goto run
:run
start "" pythonw app.py
exit /b 0
:nopython
echo [未找到 Python] 请先安装 Python 3.11 以上版本,并勾选 Add Python to PATH
pause
exit /b 1
:failinstall
echo 依赖安装失败,请检查网络后重新双击本文件
pause
exit /b 1
