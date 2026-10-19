from locust import HttpUser, task, between
import random

# Lista de 48 DNIs reales del Padrón Electoral UNAP
DNIS_MUESTRA = [
    '73312120', '48110391', '29619160', '47526446', '71324540',
    '73029115', '73298596', '46830207', '70143643', '01242200',
    '42305280', '43709253', '74528014', '72631449', '72176999',
    '48677897', '74905619', '75282968', '70218304', '74646717',
    '70126134', '73219981', '01343815', '74888258', '80516451',
    '43140968', '70101994', '71649346', '41811656', '70235895',
    '02422961', '70207085', '02436699', '71500956', '44000767',
    '45590336', '75851711', '70093696', '45894275', '47196874',
    '40389452', '72365933', '73624376', '70828266', '74297575',
    '70830350', '73265453', '75617296'
]


class UsuarioTradicional(HttpUser):
    """
    ARQUITECTURA 1: API REST Tradicional
    Lectura y escritura síncrona bloqueante directa en PostgreSQL.
    """
    weight = 1
    wait_time = between(0.05, 0.15)

    @task
    def test_tradicional(self):
        dni = random.choice(DNIS_MUESTRA)
        self.client.get(
            f"/api/v1/tradicional/{dni}",
            name="[Arq 1] API Tradicional (Sincrona)"
        )


class UsuarioLambda(HttpUser):
    """
    ARQUITECTURA 2: Arquitectura Lambda
    Batch Layer (PostgreSQL) + Speed Layer (Deltas en memoria) + Serving Layer.
    """
    weight = 1
    wait_time = between(0.05, 0.15)

    @task
    def test_lambda(self):
        dni = random.choice(DNIS_MUESTRA)
        self.client.get(
            f"/api/v1/lambda/{dni}",
            name="[Arq 2] Arquitectura Lambda (Batch + Speed)"
        )


class UsuarioKappa(HttpUser):
    """
    ARQUITECTURA 3: Arquitectura Kappa
    Flujo de Streaming Puro + Serving Layer en memoria (< 2 ms).
    """
    weight = 1
    wait_time = between(0.05, 0.15)

    @task
    def test_kappa(self):
        dni = random.choice(DNIS_MUESTRA)
        self.client.get(
            f"/api/v1/kappa/{dni}",
            name="[Arq 3] Arquitectura Kappa (Streaming Puro)"
        )
