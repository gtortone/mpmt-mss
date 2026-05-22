
def rpc_service(name: str = None):
    # class wrapper
    def wrapper(cls):
        cls._rpc_service_name = name or cls.__name__
        return cls
    return wrapper

def rpc_method(func):
    # method wrapper
    func._rpc_exposed = True
    return func
