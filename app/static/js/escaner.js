function onScanSuccess(decodedText, decodedResult) {
    // Detener el escáner momentáneamente para evitar múltiples peticiones seguidas
    html5QrcodeScanner.clear();

    // Enviar el texto decodificado del QR a Flask mediante Fetch (AJAX)
    fetch('/alumno/escanear', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ qr_data: decodedText })
    })
    .then(response => response.json())
    .then(data => {
        const mensajeDiv = document.getElementById('resultadoMensaje');
        mensajeDiv.style.display = 'block';
        
        if (data.status === 'success') {
            mensajeDiv.className = 'mensaje exito';
            mensajeDiv.innerHTML = "✅ " + data.message;
        } else {
            mensajeDiv.className = 'mensaje error';
            mensajeDiv.innerHTML = "❌ " + data.message;
            
            // Permitir reintentar el escaneo después de 4 segundos si hubo error
            setTimeout(() => {
                mensajeDiv.style.display = 'none';
                html5QrcodeScanner.render(onScanSuccess, onScanFailure);
            }, 4000);
        }
    })
    .catch(error => {
        console.error('Error:', error);
    });
}

function onScanFailure(error) {
    // Ignoramos los errores menores de lectura para no saturar la consola del navegador
}

// Inicializar el escáner usando la librería html5-qrcode
const html5QrcodeScanner = new Html5QrcodeScanner(
    "reader", { fps: 10, qrbox: { width: 250, height: 250 } }, /* verbose=false */
);
html5QrcodeScanner.render(onScanSuccess, onScanFailure);