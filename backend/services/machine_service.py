"""Machine Service — deteccion y registro de maquinas."""
import os
import sys
import platform
import subprocess
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from backend.database import get_connection, AtomicAction, init_db


def detect_local_machine() -> dict:
    """Detecta el hardware de la maquina local y la registra en la BD."""
    import multiprocessing

    # Detectar hardware
    chip = platform.processor() or platform.machine()
    ram_gb = None
    try:
        ram_bytes = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
        ram_gb = round(ram_bytes / (1024**3), 1)
    except (AttributeError, ValueError):
        pass

    hostname = platform.node()

    # Detectar engines disponibles
    engines = []
    for cmd, name in [("llama-cli", "llama-cpp"), ("mlx_lm.benchmark", "mlx")]:
        if subprocess.run(["which", cmd], capture_output=True).returncode == 0:
            engines.append(name)

    # Detectar disco
    disk_total = None
    disk_free = None
    try:
        stat = os.statvfs('/')
        disk_total = round(stat.f_frsize * stat.f_blocks / (1024**3), 1)
        disk_free = round(stat.f_frsize * stat.f_bfree / (1024**3), 1)
    except:
        pass

    machine_info = {
        "name": f"{chip} Local",
        "host": "localhost",
        "port": 22,
        "user": os.environ.get("USER", "admin"),
        "chip": chip,
        "ram_gb": ram_gb,
        "disk_total_gb": disk_total,
        "disk_free_gb": disk_free,
        "engines": engines,
        "is_local": 1,
        "status": "online",
        "hostname": hostname,
    }

    # Asegurar que la BD existe
    init_db()
    db = get_connection()
    with AtomicAction(db, "detect_local_machine", "machine", request=machine_info):
        existing = db.execute("SELECT id FROM machines WHERE is_local=1").fetchone()
        if existing:
            db.execute("""
                UPDATE machines SET chip=?, ram_gb=?, disk_total_gb=?, disk_free_gb=?,
                    engines=?, status='online', last_seen=strftime('%Y-%m-%dT%H:%M:%S','now')
                WHERE id=?
            """, (chip, ram_gb, disk_total, disk_free, ",".join(engines), existing["id"]))
            machine_info["id"] = existing["id"]
        else:
            cur = db.execute("""
                INSERT INTO machines (name, host, port, user, chip, ram_gb,
                    disk_total_gb, disk_free_gb, engines, is_local, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 'online')
            """, (machine_info["name"], machine_info["host"], machine_info["port"],
                  machine_info["user"], chip, ram_gb, disk_total, disk_free,
                  ",".join(engines)))
            machine_info["id"] = cur.lastrowid
        db.commit()
    db.close()

    return machine_info


if __name__ == "__main__":
    info = detect_local_machine()
    print(f"Maquina detectada: {info['name']}")
    print(f"  Chip: {info['chip']}")
    print(f"  RAM: {info['ram_gb']} GB")
    print(f"  Disco: {info['disk_total_gb']} GB total, {info['disk_free_gb']} GB libre")
    print(f"  Engines: {info['engines']}")
