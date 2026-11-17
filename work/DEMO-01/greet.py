def greet(name):
    if name is None:
        raise TypeError("name must be a string, got None")
    return "Hallo, " + name
