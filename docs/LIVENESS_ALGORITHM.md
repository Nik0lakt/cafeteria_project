# Liveness Detection Algorithm

## Problem Statement

Face verification alone is insufficient for secure payments — an attacker can present a printed photo or phone screen showing the victim's face. We need to distinguish a live person from a static image in real-time, using only a standard webcam.

## Approach: Variance-Based Liveness

### Key Insight

A live human face exhibits constant micro-movements (breathing, micro-saccades, head sway) that cause small but measurable variations in face embedding distances between consecutive frames. A static image (photo/screen) produces near-identical embeddings every frame.

### Algorithm

```
Input: stream of camera frames, reference embedding E_ref
Parameters:
  MATCHES_NEEDED = 4      (minimum frames with face match)
  VARIANCE_NEEDED = 0.02  (minimum distance range)
  FACE_TOLERANCE = 0.55   (cosine distance threshold for match)

State per session:
  match_count = 0
  dist_max = -inf
  dist_min = +inf

For each frame:
  1. Extract face embedding E_frame
  2. Compute distance: d = ||E_ref - E_frame||
  3. If d <= FACE_TOLERANCE:
       match_count += 1
       dist_max = max(dist_max, d)
       dist_min = min(dist_min, d)
  4. variance = dist_max - dist_min
  5. If match_count >= MATCHES_NEEDED AND variance >= VARIANCE_NEEDED:
       → PASS (live face confirmed)
```

### Why It Works

| Scenario | Distance Range | Result |
|----------|---------------|--------|
| Live face | 0.03 - 0.08 | PASS (range > 0.02) |
| Printed photo | 0.001 - 0.005 | FAIL (range < 0.02) |
| Phone screen | 0.005 - 0.015 | FAIL (range < 0.02) |

## Evolution of the Approach

### v1: EAR-Based Blink Detection
- Used Eye Aspect Ratio (EAR) to detect blinks
- Required user to blink on command
- **Problems:** unreliable with glasses, poor lighting; some users couldn't trigger consistently; added friction to payment flow

### v2: Face-Match Voting (3 frames)
- Required 3 consecutive frames with face match
- No anti-spoofing — photos passed easily
- **Problem:** zero protection against spoofing

### v3: Variance-Based Detection (current)
- Passive — no user action required
- Exploits physics: real faces move, photos don't
- ~2-3 seconds to complete (4 frames at 500ms intervals)
- **Tradeoff:** slightly slower than pure matching, but resistant to photo attacks

## Parameters and Tuning

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `MATCHES_NEEDED` | 4 | Enough frames to measure meaningful variance |
| `VARIANCE_NEEDED` | 0.02 | Empirically tested: live faces show 0.03-0.08, photos show <0.015 |
| `FACE_TOLERANCE` | 0.55 | Stricter than default 0.6; reduces false positives while accepting real users |

## Limitations

1. **Video replay** — a video of the person would pass (future mitigation: texture analysis)
2. **3D masks** — high-quality masks could pass (future: depth sensor)
3. **Lighting sensitivity** — very dark environments reduce embedding quality
4. **Identical twins** — cannot distinguish (inherent face_recognition limitation)

## References

- face_recognition library: dlib's ResNet face encoder (128-dimensional embeddings)
- Distance metric: Euclidean distance in embedding space
- Threshold selection based on empirical testing with 10+ subjects
