import os
import sys
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
from tkinter import ttk
from collections import defaultdict
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

# Define file categories and their extensions
FILE_TYPES = {
    'Images': ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp', '.tiff'],
    'Videos': ['.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv'],
    'Archives': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz'],
    'Executables': ['.exe', '.dmg', '.pkg', '.appimage', '.deb', '.msi'],
    'Documents': ['.pdf', '.doc', '.docx', '.txt', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp'],
    'Audio': ['.mp3', '.wav', '.flac', '.aac', '.ogg'],
    'Code': ['.py', '.html', '.css', '.js', '.c', '.cpp', '.java', '.sh', '.json', '.xml'],
    'Fonts': ['.ttf', '.otf', '.woff', '.woff2'],
    'Disk Images': ['.iso', '.img', '.vdi']
}

class FileOrganizerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("File Organizer")
        self.root.geometry("800x800")
        self.root.resizable(False, False)
        
        # Try to set the icon from the system path
        try:
            icon_path = "/usr/share/pixmaps/file-organizer.png"
            if os.path.exists(icon_path):
                icon = tk.PhotoImage(file=icon_path)
                self.root.iconphoto(True, icon)
            else:
                self.root.iconbitmap("@/usr/share/pixmaps/folder.xbm")
        except:
            pass  # If icon loading fails, continue without it
            
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.selected_directory = ""
        self.checkbox_vars = {}
        self.file_types_config = FILE_TYPES.copy()
        self.last_move_log = []

        # --- Main Layout ---
        self.main_frame = tk.Frame(self.root, padx=10, pady=10)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Top section for directory and checkboxes
        top_frame = tk.Frame(self.main_frame)
        top_frame.pack(fill=tk.X, pady=5)

        self.dir_label = tk.Label(top_frame, text="No directory selected.", wraplength=350, justify=tk.LEFT)
        self.dir_label.pack(side=tk.LEFT, padx=10)

        select_btn = tk.Button(top_frame, text="Select Directory", command=self.select_directory)
        select_btn.pack(side=tk.LEFT, padx=10)

        # Checkboxes for file types
        self.checkbox_frame = tk.LabelFrame(self.main_frame, text="Select Categories", padx=10, pady=5)
        self.checkbox_frame.pack(pady=10, fill=tk.X)

        # Checkbox for empty folder deletion
        self.delete_empty_folders_var = tk.BooleanVar(value=False)
        self.delete_empty_folders_chk = tk.Checkbutton(self.main_frame, text="Delete empty folders",
                                                      variable=self.delete_empty_folders_var)
        self.delete_empty_folders_chk.pack(pady=5, anchor="w")

        # Progress bar
        self.progress_bar = ttk.Progressbar(self.main_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(pady=10, fill=tk.X)
        self.progress_bar_label = tk.Label(self.main_frame, text="Ready.")
        self.progress_bar_label.pack()

        # Organize and Undo buttons - CREATE THEM BEFORE THEY ARE USED
        btn_frame = tk.Frame(self.main_frame)
        btn_frame.pack(pady=10)
        self.organize_btn = tk.Button(btn_frame, text="Organize", state=tk.DISABLED, command=self.organize_files)
        self.organize_btn.pack(side=tk.LEFT, padx=5)
        self.undo_btn = tk.Button(btn_frame, text="Undo Last Action", state=tk.DISABLED, command=self.undo_last_action)
        self.undo_btn.pack(side=tk.LEFT, padx=5)

        # Status log text widget
        self.log_text = tk.Text(self.main_frame, height=5, state=tk.DISABLED, bg='light gray', fg='black')
        self.log_text.pack(pady=5, fill=tk.BOTH)

        # Matplotlib Plot Section
        self.fig, self.ax = plt.subplots(figsize=(6, 4))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.main_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        #self.canvas_widget.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=10)
        self.update_plot({})

        # Menu Bar
        menubar = tk.Menu(root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)
        options_menu = tk.Menu(menubar, tearoff=0)
        options_menu.add_command(label="Edit File Types", command=self.edit_file_types)
        menubar.add_cascade(label="Options", menu=options_menu)
        root.config(menu=menubar)
        
        # NOW CALL THE METHOD AFTER ALL WIDGETS ARE CREATED
        self._create_category_checkboxes()

    def on_closing(self):
        """Destroys the root window and quits the main loop."""
        if messagebox.askokcancel("Quit", "Do you want to quit the application?"):
            # Close matplotlib figure to prevent background threads
            plt.close(self.fig)
        # Destroy canvas widget
            if self.canvas:
                self.canvas.get_tk_widget().destroy()
            
            self.root.destroy()
            sys.exit(0) # Ensures the Python process terminates immediately.

    def _create_category_checkboxes(self):
        """Creates/recreates category checkboxes based on current file_types_config."""
        for widget in self.checkbox_frame.winfo_children():
            widget.destroy()
        
        self.checkbox_vars = {}
        row, col = 0, 0
        for category in self.file_types_config.keys():
            var = tk.BooleanVar(value=True)
            chk = tk.Checkbutton(self.checkbox_frame, text=category, variable=var,
                                 command=self.update_organize_button_state)
            chk.grid(row=row, column=col, sticky="w", padx=5, pady=2)
            self.checkbox_vars[category] = var
            col += 1
            if col > 2:
                col = 0
                row += 1
        self.update_organize_button_state()

    def select_directory(self):
        """Opens a directory dialog and updates the GUI and plot."""
        directory = filedialog.askdirectory()
        if directory:
            self.selected_directory = directory
            self.dir_label.config(text=f"Selected directory:\n{directory}")
            self.check_files_in_directory()
            self.canvas_widget.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, pady=10)
        else:
            self.dir_label.config(text="No directory selected.")
            self.selected_directory = ""
            self.update_plot({})
            self.canvas_widget.pack_forget()

        self.update_organize_button_state()

    def check_files_in_directory(self):
        """Checks if the selected directory has any files and updates statistics."""
        if not self.selected_directory:
            self.update_plot({})
            return

        file_counts = defaultdict(int)
        total_files = 0
        has_files_to_organize = False

        for item in os.listdir(self.selected_directory):
            full_path = os.path.join(self.selected_directory, item)
            if os.path.isfile(full_path):
                total_files += 1
                has_files_to_organize = True
                file_extension = os.path.splitext(item)[1].lower()
                
                found_category = False
                for category, extensions in self.file_types_config.items():
                    if file_extension in extensions:
                        file_counts[category] += 1
                        found_category = True
                        break
                if not found_category:
                    file_counts['Other'] += 1

        self.update_plot(file_counts)
        self.progress_bar['value'] = 0
        self.progress_bar_label.config(text=f"Found {total_files} files.")
        self.update_organize_button_state()
        
        if not has_files_to_organize:
            messagebox.showinfo("No Files Found", "There are no files to be organized in the selected directory.")
            self.organize_btn.config(state=tk.DISABLED)
            
    def update_plot(self, file_counts):
        """Updates the pie chart with new file statistics."""
        self.ax.clear()
        labels, sizes = [], []
        for category, count in file_counts.items():
            if count > 0:
                labels.append(category)
                sizes.append(count)

        if sizes:
            self.ax.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=90)
            self.ax.axis('equal')
            self.ax.set_title("Directory File Distribution")
        else:
            self.ax.text(0.5, 0.5, "Select a directory to view statistics", horizontalalignment='center', 
                         verticalalignment='center', transform=self.ax.transAxes, fontsize=12)
            self.ax.set_title("Directory File Distribution")

        self.canvas.draw()

    def update_organize_button_state(self):
        """Enables/disables buttons based on conditions."""
        is_directory_selected = bool(self.selected_directory)
        is_any_category_selected = any(var.get() for var in self.checkbox_vars.values())
        
        if is_directory_selected and is_any_category_selected:
            self.organize_btn.config(state=tk.NORMAL)
        else:
            self.organize_btn.config(state=tk.DISABLED)

        if self.last_move_log:
            self.undo_btn.config(state=tk.NORMAL)
        else:
            self.undo_btn.config(state=tk.DISABLED)

    def log_message(self, message):
        """Adds a message to the status log."""
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def organize_files(self):
        """Main function to organize files based on selected categories."""
        if not self.selected_directory:
            messagebox.showerror("Error", "Please select a directory first.")
            return

        self.last_move_log = []
        files_to_move = []
        
        for filename in os.listdir(self.selected_directory):
            file_path = os.path.join(self.selected_directory, filename)
            if os.path.isdir(file_path):
                continue
            
            file_extension = os.path.splitext(filename)[1].lower()
            target_category = None
            
            for category, extensions in self.file_types_config.items():
                if self.checkbox_vars[category].get() and file_extension in extensions:
                    target_category = category
                    break

            if target_category:
                # Use the category name as the folder name
                folder_name = category
                target_dir = os.path.join(self.selected_directory, folder_name)
                files_to_move.append({'src': file_path, 'dest_dir': target_dir, 'filename': filename})

        total_files = len(files_to_move)
        if total_files == 0:
            messagebox.showinfo("No Files", "No files to organize based on your selections.")
            return

        self.progress_bar['maximum'] = total_files
        self.log_message(f"Starting to organize {total_files} files...")

        for i, file_info in enumerate(files_to_move):
            src = file_info['src']
            dest_dir = file_info['dest_dir']
            filename = file_info['filename']

            if not os.path.exists(dest_dir):
                try:
                    os.makedirs(dest_dir)
                    self.log_message(f"Created directory: {dest_dir}")
                except Exception as e:
                    self.log_message(f"Error creating directory {dest_dir}: {e}")
                    continue

            try:
                dest_path = os.path.join(dest_dir, filename)
                shutil.move(src, dest_path)
                self.last_move_log.append({'src': dest_path, 'dest': src})
                self.log_message(f"Moved '{filename}' to '{os.path.basename(dest_dir)}'")
                
            except Exception as e:
                self.log_message(f"Error moving '{filename}': {e}")
            
            self.progress_bar['value'] = i + 1
            self.root.update_idletasks()
        
        # Delete empty folders if the option is checked
        if self.delete_empty_folders_var.get():
            self.delete_empty_folders()

        messagebox.showinfo("Success", f"Successfully organized {total_files} files!")
        self.check_files_in_directory()
        self.update_organize_button_state()
    
    def undo_last_action(self):
        """Reverses the last organization action."""
        if not self.last_move_log:
            messagebox.showinfo("No Action to Undo", "There is no recent organization action to undo.")
            return

        response = messagebox.askyesno("Undo Action", "Are you sure you want to undo the last organization action?")
        if not response:
            return

        self.log_message("Attempting to undo last organization...")
        undone_count = 0
        
        # The log is in order of moves, so we reverse it to undo from the last move
        for move in reversed(self.last_move_log):
            src_path = move['src']
            dest_path = move['dest']
            try:
                shutil.move(src_path, dest_path)
                self.log_message(f"Moved '{os.path.basename(src_path)}' back to original location.")
                undone_count += 1
            except Exception as e:
                self.log_message(f"Error undoing move for '{os.path.basename(src_path)}': {e}")

        self.last_move_log = []
        messagebox.showinfo("Undo Complete", f"Successfully undid {undone_count} file moves.")
        self.check_files_in_directory()
        self.update_organize_button_state()

    def delete_empty_folders(self):
        """Deletes any empty folders in the selected directory."""
        deleted_count = 0
        self.log_message("Checking for empty folders to delete...")
        for item in os.listdir(self.selected_directory):
            full_path = os.path.join(self.selected_directory, item)
            if os.path.isdir(full_path) and not os.listdir(full_path):
                try:
                    os.rmdir(full_path)
                    self.log_message(f"Deleted empty folder: {item}")
                    deleted_count += 1
                except OSError as e:
                    self.log_message(f"Error deleting {item}: {e}")
        if deleted_count > 0:
            messagebox.showinfo("Empty Folders Deleted", f"Deleted {deleted_count} empty folders.")
        
        self.check_files_in_directory()

    def edit_file_types(self):
        """Opens a new window for editing file type extensions."""
        EditFileTypesWindow(self.root, self.file_types_config, self.on_file_types_updated)

    def on_file_types_updated(self, new_file_types):
        """Callback function when file types are updated in the edit window."""
        self.file_types_config = new_file_types
        self._create_category_checkboxes()
        self.check_files_in_directory()
        self.log_message("File types configuration updated.")

class EditFileTypesWindow:
    def __init__(self, master, current_file_types, callback):
        self.top = tk.Toplevel(master)
        self.top.title("Edit File Types")
        self.top.transient(master)
        self.top.grab_set()
        self.top.geometry("900x500")
        self.top.resizable(False, True)

        self.current_file_types = current_file_types.copy()
        self.callback = callback
        self.entries = {}

        tk.Label(self.top, text="Edit Folder Names & Extensions (comma-separated, include '.')", font=('Arial', 10, 'bold')).pack(pady=5)

        # Frame for scrollable content
        canvas = tk.Canvas(self.top)
        scrollbar = tk.Scrollbar(self.top, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas)

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Add existing categories
        for category, extensions in self.current_file_types.items():
            self._add_category_row(scrollable_frame, category, extensions)
        
        # Add new category button
        add_button_frame = tk.Frame(scrollable_frame)
        add_button_frame.pack(pady=5, fill=tk.X)
        tk.Button(add_button_frame, text="Add New Category", command=lambda: self._add_category_row(scrollable_frame)).pack(side=tk.LEFT, padx=5)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Save and Cancel buttons
        btn_frame = tk.Frame(self.top)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Save Changes", command=self.save_changes).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Cancel", command=self.top.destroy).pack(side=tk.LEFT, padx=5)

    def _add_category_row(self, parent_frame, category="", extensions=None):
        """Adds a row for a category to the edit window."""
        row_frame = tk.Frame(parent_frame)
        row_frame.pack(fill=tk.X, padx=5, pady=2)

        # Category Name Entry (for both existing and new)
        tk.Label(row_frame, text="Folder Name:").pack(side=tk.LEFT, padx=2)
        name_entry = tk.Entry(row_frame, width=15)
        name_entry.pack(side=tk.LEFT, padx=2)
        if category:
            name_entry.insert(0, category)

        # Extensions Entry
        tk.Label(row_frame, text="Extensions:").pack(side=tk.LEFT, padx=5)
        ext_entry = tk.Entry(row_frame, width=30)
        if extensions:
            ext_str = ", ".join(extensions)
            ext_entry.insert(0, ext_str)
        ext_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        
        self.entries[name_entry] = ext_entry # Store mapping of name to extensions

        delete_btn = tk.Button(row_frame, text="X", command=lambda: self._delete_category_row(row_frame, name_entry))
        delete_btn.pack(side=tk.RIGHT, padx=2)
    
    def _delete_category_row(self, row_frame, name_entry):
        """Removes a category row from the edit window."""
        if name_entry in self.entries:
            del self.entries[name_entry]
        row_frame.destroy()

    def save_changes(self):
        """Collects changes from entries and updates the file types."""
        new_file_types = {}
        for name_entry, ext_entry in self.entries.items():
            folder_name = name_entry.get().strip()
            extensions_str = ext_entry.get().strip()

            if not folder_name or not extensions_str:
                messagebox.showwarning("Incomplete Entry", "Please provide both a folder name and at least one extension.")
                return

            extensions = [ext.strip().lower() for ext in extensions_str.split(',') if ext.strip()]
            extensions = [ext if ext.startswith('.') else f'.{ext}' for ext in extensions]
            extensions = list(set(extensions))

            if folder_name in new_file_types:
                messagebox.showwarning("Duplicate Folder Name", f"The folder name '{folder_name}' is defined multiple times.")
                return

            new_file_types[folder_name] = extensions
        
        self.callback(new_file_types)
        self.top.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    # Set window class BEFORE creating the app
    try:
        root.wm_class("file-organizer")
    except:
        pass
    app = FileOrganizerApp(root)
    root.mainloop()
