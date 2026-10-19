-- =============================================================================
-- ESQUEMA DE BASE DE DATOS — Plataforma de Consulta Electoral (Mock / Estructura)
-- Datos privados protegidos. Este archivo contiene únicamente la estructura DDL
-- y registros de demostración anónimos.
-- =============================================================================

CREATE TABLE IF NOT EXISTS padron (
    dni VARCHAR(20) PRIMARY KEY,
    codigo VARCHAR(20),
    ap_paterno VARCHAR(100),
    ap_materno VARCHAR(100),
    nombres VARCHAR(150),
    tipo VARCHAR(50),
    fac_cod VARCHAR(10),
    facultad VARCHAR(300),
    esc_cod VARCHAR(10),
    escuela_profesional VARCHAR(300)
);

CREATE INDEX IF NOT EXISTS idx_padron_codigo ON padron(codigo);
CREATE INDEX IF NOT EXISTS idx_padron_tipo ON padron(tipo);

CREATE TABLE IF NOT EXISTS electores (
    dni VARCHAR(20) PRIMARY KEY REFERENCES padron(dni) ON DELETE CASCADE,
    mesa VARCHAR(10),
    posicion INTEGER,
    local_votacion VARCHAR(300)
);

CREATE INDEX IF NOT EXISTS idx_electores_mesa ON electores(mesa);

CREATE TABLE IF NOT EXISTS miembros_mesa (
    id SERIAL PRIMARY KEY,
    dni_miembro VARCHAR(20) REFERENCES padron(dni) ON DELETE CASCADE,
    numero_mesa VARCHAR(10) NOT NULL,
    local_mesa VARCHAR(300),
    facultad_mesa VARCHAR(300),
    cargo VARCHAR(60),
    miembro VARCHAR(20),
    categoria VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_miembros_dni ON miembros_mesa(dni_miembro);

CREATE TABLE IF NOT EXISTS log_consultas (
    id SERIAL PRIMARY KEY,
    documento VARCHAR(20),
    tipo_busqueda VARCHAR(10),
    fecha_hora TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_cliente VARCHAR(50),
    fue_encontrado BOOLEAN,
    tipo_persona VARCHAR(50),
    es_miembro_mesa BOOLEAN DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_log_consultas_doc ON log_consultas(documento);

-- =============================================================================
-- DATOS ANÓNIMOS DE DEMOSTRACIÓN (Para pruebas y despliegue inicial)
-- =============================================================================
INSERT INTO padron (dni, codigo, ap_paterno, ap_materno, nombres, tipo, facultad, escuela_profesional)
VALUES 
    ('73312120', '200101', 'ALCA', 'LOPEZ', 'JHONY', 'ESTUDIANTE DE PREGRADO', 'INGENIERIA', 'INGENIERIA DE SISTEMAS'),
    ('48110391', '200102', 'QUISPE', 'MAMANI', 'CARLOS', 'ESTUDIANTE DE PREGRADO', 'INGENIERIA', 'INGENIERIA MECANICA'),
    ('29619160', '200103', 'FLORES', 'CONDORI', 'MARIA', 'DOCENTE', 'CIENCIAS', 'ESTADISTICA'),
    ('47526446', '200104', 'APAZA', 'CHURA', 'PEDRO', 'ESTUDIANTE DE PREGRADO', 'CIENCIAS CONTABLES', 'CONTABILIDAD')
ON CONFLICT (dni) DO NOTHING;

INSERT INTO electores (dni, mesa, posicion, local_votacion)
VALUES 
    ('73312120', '0101', 1, 'PABELLON DE INGENIERIA'),
    ('48110391', '0101', 2, 'PABELLON DE INGENIERIA'),
    ('29619160', '0102', 1, 'EDIFICIO ADMINISTRATIVO'),
    ('47526446', '0103', 1, 'CIENCIAS JURIDICAS')
ON CONFLICT (dni) DO NOTHING;
