import os
import sys
import tempfile
from pathlib import Path

# Las pruebas usan una carpeta de datos temporal: no tocan la base de la demo.
os.environ["AGENTE_DATOS"] = tempfile.mkdtemp(prefix="agente-test-")
sys.path.insert(0, str(Path(__file__).parent.parent))
