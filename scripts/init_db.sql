-- One database, three schemas — one per service
-- Each service's DB user only gets access to its own schema

CREATE SCHEMA IF NOT EXISTS users;
CREATE SCHEMA IF NOT EXISTS products;
CREATE SCHEMA IF NOT EXISTS orders;

-- Grant schema ownership to the shopflow user
GRANT ALL ON SCHEMA users TO shopflow;
GRANT ALL ON SCHEMA products TO shopflow;
GRANT ALL ON SCHEMA orders TO shopflow;
