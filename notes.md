# Предложения по улучшению стабильности liveness-проверки

## 1. Метод голосования по N кадрам (Voting Window)

**Проблема:** единственный кадр с плохим освещением или повёрнутым лицом даёт false negative.

**Решение:** накапливать расстояния face_distance за последние N кадров и принимать решение по большинству.

```python
# В LivenessSession добавить поле:
match_history = Column(JSON, default=list)  # список булевых значений

# В liveness_frame:
MATCH_WINDOW = 5
MATCH_THRESHOLD = 3  # из 5 кадров хотя бы 3 должны совпасть

history = sess.match_history or []
history.append(face_match)
if len(history) > MATCH_WINDOW:
    history = history[-MATCH_WINDOW:]
sess.match_history = history

votes = sum(history)
face_confirmed = votes >= MATCH_THRESHOLD and len(history) >= MATCH_WINDOW
if face_confirmed and sess.blink_count >= 2:
    sess.passed = True
```

**Плюс:** один «смазанный» кадр не ломает результат.  
**Минус:** задержка решения на N*FRAME_INTERVAL мс.

---

## 2. Предфильтрация кадра по освещённости (Brightness Gate)

**Проблема:** слабо освещённые кадры дают некачественные embeddings и завышают face_distance.

**Решение:** вычислять среднюю яркость кадра на клиенте перед отправкой; слишком тёмные кадры пропускать.

```javascript
// В captureFrame() или перед fetch:
function isFrameBright(canvas, minMean = 50) {
    const ctx = canvas.getContext('2d');
    const data = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let sum = 0;
    for (let i = 0; i < data.length; i += 4) {
        sum += 0.299 * data[i] + 0.587 * data[i+1] + 0.114 * data[i+2]; // luma
    }
    return (sum / (data.length / 4)) >= minMean;
}
```

Если `!isFrameBright(canvas)` — показываем "Улучшите освещение" и пропускаем запрос.

**Плюс:** не тратим запросы на заведомо плохие кадры; быстрая обратная связь пользователю.  
**Минус:** добавляет CPU-нагрузку на клиенте (~2 мс на кадр 640×480).

---

## 3. Нормализация яркости/контрастности на бэкенде (CLAHE)

**Проблема:** разные камеры и условия освещения дают сильно различающиеся embeddings для одного лица.

**Решение:** применять CLAHE (Contrast Limited Adaptive Histogram Equalization) перед вычислением embedding.

```python
# В get_face_embedding_and_ear(), перед face_locations:
lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
l, a, b = cv2.split(lab)
clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
l = clahe.apply(l)
img = cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2BGR)
rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
```

**Важно:** если включить, нужно **пере-энrollить** всех пользователей с тем же фильтром,
иначе enrolled-embedding и live-embedding будут в разных цветовых пространствах.

**Плюс:** +5–10% стабильности при слабом/неравномерном освещении.  
**Минус:** небольшой прирост времени обработки (~10 мс); требует повторного энrolла.

---

## Текущие параметры (к сведению)

| Параметр | Значение | Описание |
|---|---|---|
| `FACE_RECOGNITION_TOLERANCE` | `0.55` (env) | Порог принятия совпадения |
| `EAR_CLOSE_THRESHOLD` | `0.20` | EAR ниже этого — начало моргания |
| `EAR_OPEN_THRESHOLD` | `0.25` | EAR выше этого — конец моргания |
| `EAR_MIN_BLINK` | `0.12` | Минимум EAR за фазу закрытия (anti-spoofing) |
| `MAX_FRAMES` | `60` | Таймаут сессии в кадрах |
| `FRAME_INTERVAL` | `400 мс` | Пауза между отправками кадров |
