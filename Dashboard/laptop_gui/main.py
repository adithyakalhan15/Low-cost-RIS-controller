import customtkinter as ctk
from .gui_app import RISMasterTabbedGUI

def main():
    root = ctk.CTk()
    app = RISMasterTabbedGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()

if __name__ == "__main__":
    main()
