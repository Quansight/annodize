__all__ = 'context',

with __import__('importnb').Notebook():
    from .annodize import context
    

def load_ipython_extension(shell):
    annodize.load_ipython_extension(shell)
    from . import formatters
    formatters.load_ipython_extension(shell)
    
def unload_ipython_extension(shell):
    annodize.unload_ipython_extension(shell)
    from . import formatters
    formatters.unload_ipython_extension(shell)