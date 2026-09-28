"""Recogida de una sola fuente sin procesar después (para cargas iniciales en paralelo)."""
import sys, time
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
from concordia import db
from concordia.recoger import recoger
con = db.connect()
db.init(con, catalogos=False)
t = recoger(con, fuentes=sys.argv[1].split(","), completo="--completo" in sys.argv,
            log=lambda m: print(time.strftime("%H:%M:%S"), m, flush=True))
print("años tocados:", {k: sorted(v) for k, v in t.items()})
