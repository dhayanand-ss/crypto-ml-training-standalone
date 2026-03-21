class ProjectOutputFormatter:
    """Dummy formatter to replace missing dependency."""
    def __init__(self):
        pass
    
    def print_header(self, text):
        print(f"\n{'='*50}\n{text}\n{'='*50}")
        
    def print_section(self, text):
        print(f"\n--- {text} ---")
