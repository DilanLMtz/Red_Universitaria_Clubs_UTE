-- Tabla de Usuarios (Sirve para administradores y coordinadores)
CREATE TABLE Usuarios (
    id_usuario INT AUTO_INCREMENT PRIMARY KEY,
    nombre_completo VARCHAR(100) NOT NULL,
    correo VARCHAR(100) UNIQUE NOT NULL,
    contrasena VARCHAR(255) NOT NULL, -- Recuerda encriptarlas (ej. con bcrypt en Python)
    rol ENUM('Coordinador', 'Administrador') NOT NULL
);

-- Tabla de Clubs
CREATE TABLE Clubs (
    id_club INT AUTO_INCREMENT PRIMARY KEY,
    nombre_club VARCHAR(100) NOT NULL,
    descripcion TEXT,
    id_coordinador INT,
    capacidad_maxima INT,
    FOREIGN KEY (id_coordinador) REFERENCES Usuarios(id_usuario)
);

-- Tabla de Horarios
CREATE TABLE Horarios (
    id_horario INT AUTO_INCREMENT PRIMARY KEY,
    id_club INT,
    dia_semana ENUM('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado'),
    hora_inicio TIME,
    hora_fin TIME,
    lugar VARCHAR(100),
    FOREIGN KEY (id_club) REFERENCES Clubs(id_club)
);

-- Tabla de Alumnos (Se llena leyendo el archivo Excel)
CREATE TABLE Alumnos (
    matricula VARCHAR(20) PRIMARY KEY,
    nombre_completo VARCHAR(100) NOT NULL,
    contrasena VARCHAR(255) NOT NULL, -- contraseña generada
    carrera VARCHAR(100)
);

-- Tabla puente: Qué alumno está en qué club (Se llena también con el Excel)
CREATE TABLE Inscripciones (
    id_inscripcion INT AUTO_INCREMENT PRIMARY KEY,
    matricula_alumno VARCHAR(20),
    id_club INT,
    FOREIGN KEY (matricula_alumno) REFERENCES Alumnos(matricula),
    FOREIGN KEY (id_club) REFERENCES Clubs(id_club)
);

-- Tabla de Asistencias (Se llena cuando el alumno escanea el QR)
CREATE TABLE Asistencias (
    id_asistencia INT AUTO_INCREMENT PRIMARY KEY,
    matricula_alumno VARCHAR(20),
    id_club INT,
    fecha_hora DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (matricula_alumno) REFERENCES Alumnos(matricula),
    FOREIGN KEY (id_club) REFERENCES Clubs(id_club)
);