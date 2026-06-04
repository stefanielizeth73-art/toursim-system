import math


def haversine_amap(point_a, point_b):
    lat1, lon1 = float(point_a[1]), float(point_a[0])
    lat2, lon2 = float(point_b[1]), float(point_b[0])
    radius = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def polyline_distance(points):
    return sum(haversine_amap(start, end) for start, end in zip(points, points[1:]))
