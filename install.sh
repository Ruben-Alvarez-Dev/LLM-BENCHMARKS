#!/bin/bash
set -e

# LLM-BENCHMARKS — 1-Click Installer
# Uso: curl -sSL https://github.com/Ruben-Alvarez-Dev/LLM-BENCHMARKS/install.sh | bash

APP_NAME="LLM-BENCHMARKS"
REPO="https://github.com/Ruben-Alvarez-Dev/LLM-BENCHMARKS.git"
INSTALL_DIR="${HOME}/Code/${APP_NAME}"
PORT=8540

echo "================================================"
echo "  ${APP_NAME} — 1-Click Installer"
echo "================================================"
echo ""

# 1. Detectar SO y arquitectura
OS="$(uname -s)"
ARCH="$(uname -m)"
echo "[1/8] Detectando sistema: ${OS} ${ARCH}"

if [ "$OS" != "Darwin" ]; then
    echo "  ⚠️  Este proyecto esta optimizado para macOS Apple Silicon."
    echo "  Continuando de todas formas..."
fi

# 2. Verificar dependencias
echo "[2/8] Verificando dependencias..."
for cmd in python3 pip3 git ssh; do
    if command -v $cmd &>/dev/null; then
        echo "  ✅ $cmd $(command -v $cmd)"
    else
        echo "  ❌ $cmd no encontrado. Instalalo primero."
        exit 1
    fi
done

# 3. Clonar repo
echo "[3/8] Preparando directorio..."
if [ -d "$INSTALL_DIR" ]; then
    echo "  📁 Directorio existe: $INSTALL_DIR"
    cd "$INSTALL_DIR"
    git pull 2>/dev/null || echo "  ⚠️  No se pudo hacer pull"
else
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
    echo "  ✅ Clonado: $INSTALL_DIR"
fi

# 4. Instalar dependencias Python
echo "[4/8] Instalando dependencias Python..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet fastapi uvicorn pydantic python-multipart
echo "  ✅ Dependencias instaladas"

# 5. Inicializar BD
echo "[5/8] Inicializando base de datos..."
python3 -c "
from backend.database import init_db
init_db()
print('  ✅ Base de datos inicializada')
"

# 6. Detectar hardware local
echo "[6/8] Detectando hardware local..."
python3 -c "
from backend.services.machine_service import detect_local_machine
m = detect_local_machine()
print(f'  ✅ Maquina registrada: {m[\"name\"]} ({m[\"chip\"]}, {m[\"ram_gb\"]}GB)')
print(f'  🏠 Host: {m[\"host\"]}')
print(f'  ⚙️  Engines: {m[\"engines\"]}')
"

# 7. Escanear modelos locales
echo "[7/8] Escaneando modelos locales..."
python3 -c "
from backend.services.model_service import scan_local_models
count = scan_local_models()
print(f'  ✅ {count} modelos encontrados')
" 2>/dev/null || echo "  ⚠️  Escaneo omitido (configurable post-instalacion)"

# 8. Iniciar servidor
echo "[8/8] Iniciando servidor..."
echo ""
echo "================================================"
echo "  ${APP_NAME} instalado correctamente!"
echo "================================================"
echo ""
echo "  Para iniciar el servidor manualmente:"
echo "    cd ${INSTALL_DIR}"
echo "    source venv/bin/activate"
echo "    uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --reload"
echo ""
echo "  Abrir en navegador:"
echo "    http://localhost:${PORT}"
echo ""

# Iniciar servidor
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --reload &
SERVER_PID=$!
echo "  Servidor iniciado (PID: ${SERVER_PID})"

# Abrir navegador
if command -v open &>/dev/null; then
    open "http://localhost:${PORT}"
elif command -v xdg-open &>/dev/null; then
    xdg-open "http://localhost:${PORT}"
fi

echo ""
echo "  Para detener: kill ${SERVER_PID}"
echo "  Para reanudar: cd ${INSTALL_DIR} && source venv/bin/activate && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT}"
