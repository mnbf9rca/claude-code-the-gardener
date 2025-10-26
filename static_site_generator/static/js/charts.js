// Chart.js configuration for sensor data visualization

document.addEventListener('DOMContentLoaded', async function() {
    try {
        // Load sensor data
        const response = await fetch('../data/sensor_data.json');
        const sensorData = await response.json();

        // Moisture Chart
        const moistureCtx = document.getElementById('moisture-chart');
        if (moistureCtx) {
            new Chart(moistureCtx, {
                type: 'line',
                data: {
                    labels: sensorData.moisture.map(d => new Date(d.timestamp)),
                    datasets: [{
                        label: 'Moisture Level',
                        data: sensorData.moisture.map(d => d.value),
                        borderColor: '#4c9bf5',
                        backgroundColor: 'rgba(76, 155, 245, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: { unit: 'day' }
                        },
                        y: {
                            title: { display: true, text: 'Sensor Value' }
                        }
                    }
                }
            });
        }

        // Light Chart
        const lightCtx = document.getElementById('light-chart');
        if (lightCtx) {
            new Chart(lightCtx, {
                type: 'bar',
                data: {
                    labels: sensorData.light.map(d => new Date(d.timestamp)),
                    datasets: [{
                        label: 'Light Duration (minutes)',
                        data: sensorData.light.map(d => d.duration_minutes),
                        backgroundColor: '#ffd60a'
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: { unit: 'day' }
                        },
                        y: {
                            title: { display: true, text: 'Minutes' }
                        }
                    }
                }
            });
        }

        // Water Chart (Cumulative)
        const waterCtx = document.getElementById('water-chart');
        if (waterCtx) {
            new Chart(waterCtx, {
                type: 'line',
                data: {
                    labels: sensorData.water.map(d => new Date(d.timestamp)),
                    datasets: [{
                        label: 'Cumulative Water (ml)',
                        data: sensorData.water.map(d => d.cumulative_ml),
                        borderColor: '#52b788',
                        backgroundColor: 'rgba(82, 183, 136, 0.1)',
                        tension: 0.4,
                        fill: true
                    }]
                },
                options: {
                    responsive: true,
                    scales: {
                        x: {
                            type: 'time',
                            time: { unit: 'day' }
                        },
                        y: {
                            title: { display: true, text: 'Milliliters' }
                        }
                    }
                }
            });
        }

    } catch (error) {
        console.error('Error loading sensor data:', error);
    }
});
