from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import cv2
import numpy as np
import os
import pickle
import base64
from skimage.feature import hog

app = Flask(__name__)
CORS(app)

IMAGE_SIZE = (128, 128)
PIXELS_PER_CELL = (8, 8)
CELLS_PER_BLOCK = (2, 2)
ORIENTATIONS = 9

# Загружаем обученные модели
with open('models.pkl', 'rb') as f:
    models_data = pickle.load(f)

@app.route('/predict', methods=['POST'])
def predict():
    if 'file' not in request.files:
        return jsonify({'error': 'Нет файла'}), 400
    
    file = request.files['file']
    img_bytes = file.read()
    nparr = np.frombuffer(img_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_GRAYSCALE)
    
    if img is None:
        return jsonify({'error': 'Не удалось прочитать изображение'}), 400
    
    img_resized = cv2.resize(img, IMAGE_SIZE)
    
    # 1. Считаем HOG признаки для модели
    fd = hog(img_resized,
             orientations=ORIENTATIONS,
             pixels_per_cell=PIXELS_PER_CELL,
             cells_per_block=CELLS_PER_BLOCK,
             visualize=False,
             block_norm='L2-Hys')
    
    # 2. Считаем HOG для визуализации
    _, hog_image = hog(img_resized,
                       orientations=ORIENTATIONS,
                       pixels_per_cell=PIXELS_PER_CELL,
                       cells_per_block=CELLS_PER_BLOCK,
                       visualize=True,
                       block_norm='L2-Hys')
    
    # Нормализуем и кодируем в base64
    hog_norm = (hog_image / hog_image.max() * 255).astype(np.uint8)
    _, hog_buf = cv2.imencode('.jpg', hog_norm)
    hog_base64 = base64.b64encode(hog_buf).decode('utf-8')
    
    predictions = {}
    for name, data in models_data.items():
        X = fd.reshape(1, -1)
        
        # === ГЛАВНОЕ ИСПРАВЛЕНИЕ ===
        # Если scaler есть (LogReg, SVM), применяем его. 
        # Если нет (Random Forest), используем данные как есть.
        if data['scaler'] is not None:
            X = data['scaler'].transform(X)
        
        pred = int(data['model'].predict(X)[0])
        proba = None
        if hasattr(data['model'], 'predict_proba'):
            proba = float(data['model'].predict_proba(X)[0][1])
        
        predictions[name] = {'class': pred, 'probability': proba}
    
    return jsonify({
        'predictions': predictions,
        'hog_image': hog_base64
    })

@app.route('/')
def index():
    return send_from_directory('.', 'report.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)