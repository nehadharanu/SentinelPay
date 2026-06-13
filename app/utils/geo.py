import math


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return the great-circle distance in kilometres between two coordinates.

    Uses the Haversine formula. Inputs are decimal degrees.
    """
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def is_impossible_travel(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
    hours_elapsed: float,
    max_distance_km: float,
    min_hours: float,
) -> bool:
    """Return True if the distance between two locations exceeds the threshold within the time window.

    A trip is flagged as impossible travel when the elapsed time is less than
    min_hours yet the distance is greater than max_distance_km.
    """
    if hours_elapsed >= min_hours:
        return False
    distance = haversine_km(lat1, lon1, lat2, lon2)
    return distance > max_distance_km
