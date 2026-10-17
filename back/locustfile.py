from locust import HttpUser, task, between
import random

# Muestra de DNIs reales cargados en tu PostgreSQL
DNIS_MUESTRA = [
    '73313343', '75125342', '73136888', '60518572', '77699226',
    '61868518', '60758859', '71550571', '71060220', '73713189',
    '48409008', '73647969', '60746481', '77093988', '74497652',
    '75390930', '76960188', '60305343', '71641333', '70353199'
]


class ComparativaArquitecturasUser(HttpUser):
    """
    Simula tráfico concurrente hacia ambas arquitecturas para comparar:
    1. Ingesta Síncrona Bloqueante (API Tradicional)
    2. Ingesta Asíncrona Desacoplada (Streaming / Event-Driven / Kappa)
    """
    # Tiempo de espera entre peticiones de cada usuario virtual (entre 50ms y 200ms)
    wait_time = between(0.05, 0.2)

    @task(1)
    def probar_arquitectura_1_directa(self):
        """Arquitectura 1: Ingesta síncrona que bloquea la conexión DB"""
        dni = random.choice(DNIS_MUESTRA)
        self.client.get(
            f"/api/v1/benchmark/ingesta-directa/{dni}",
            name="[Arq 1] Ingesta Directa Sincrona"
        )

    @task(1)
    def probar_arquitectura_2_asincrona(self):
        """Arquitectura 2: Ingesta asíncrona desacoplada con background tasks"""
        dni = random.choice(DNIS_MUESTRA)
        self.client.get(
            f"/api/v1/benchmark/ingesta-async/{dni}",
            name="[Arq 2] Ingesta Asincrona Desacoplada"
        )
