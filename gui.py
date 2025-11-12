#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Tkinter GUI for HeyTeaAutoDraw

Features implemented:
- Menu: 文件 -> 打开文件, 设置 -> 修改当前配置, 重选画板范围
- Display image at its natural size
- Dropdown to select algorithm: 边缘 (Canny) or 扫描线 (Scan)
- 开始绘画 button to start drawing in background thread
- Log / status area
- Right-hand panel showing current configuration values (refreshable)

This uses project utilities to load/save config and to run the drawer classes.
"""
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font  # 导入字体模块
from PIL import Image, ImageTk
import os
import sys

# Ensure project root is on sys.path so local imports like `utils.*` work
sys.path.append(os.path.dirname(__file__))


from utils.config_utils import load_config, save_config, reset_config_file
from utils.coord_utils import capture_screen_region
from core.auto_drawer_canny import AutoDrawerCanny
from core.auto_drawer_scan import AutoDrawerScan


class HeyTeaGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("HeyTea AutoDrawer - GUI")
        self.geometry("1100x700")

        # Load configuration
        self.config_data = load_config()

        self.image_path = None
        self.image_pil = None
        self.image_tk = None

        self._build_menu()
        self._build_ui()

    def _build_menu(self):
        menubar = tk.Menu(self)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="打开文件", command=self.open_file)
        menubar.add_cascade(label="文件", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="修改当前配置", command=self.open_modify_config)
        settings_menu.add_command(label="重置为默认（保留画板/尺寸）", command=self.reset_config_action)
        settings_menu.add_command(label="选择画板范围", command=self.reselect_board)
        menubar.add_cascade(label="设置", menu=settings_menu)

        # --- 新增: 帮助菜单 ---
        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="查看帮助", command=self.show_help_image)
        menubar.add_cascade(label="帮助", menu=help_menu)
        # --- 帮助菜单结束 ---

        self.config(menu=menubar)

    def _build_ui(self):
        # Paned layout: left main area, right config panel
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True)

        left_frame = ttk.Frame(paned)
        right_frame = ttk.Frame(paned) 
        
        paned.add(left_frame, weight=9)
        paned.add(right_frame, weight=1)

        # --- 为控件定义更大字体样式 ---
        style = ttk.Style(self)
        
        # 获取默认字体信息
        default_font = tkinter.font.nametofont("TkDefaultFont")
        family = default_font.cget("family")
        size = default_font.cget("size")
        
        # 计算 200% 大小
        large_size = int(size * 2.0)
        
        # 配置新样式
        style.configure('Large.TLabel', font=(family, large_size))
        style.configure('Large.TButton', font=(family, large_size), padding=(10, 5))
        style.configure('Large.TMenubutton', font=(family, large_size), padding=(10, 5)) # 用于 OptionMenu
        # --- 样式定义结束 ---


        # Top: image display inside a canvas with scrollbars
        img_frame = ttk.Frame(left_frame)
        img_frame.pack(fill=tk.BOTH, expand=False)

        self.canvas = tk.Canvas(img_frame, background="#222", height=500, width=600)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas.bind('<Configure>', self._on_canvas_resize)

        # Controls below image
        ctrl_frame = ttk.Frame(left_frame)
        # --- 修改1: 去掉 fill=tk.X，让控制栏自动居中 ---
        ctrl_frame.pack(padx=6, pady=6)

        # 应用 'Large.TLabel' 样式
        ttk.Label(ctrl_frame, text="算法:", style='Large.TLabel').pack(side=tk.LEFT)
        
        self.algorithm_var = tk.StringVar(value="边缘")
        
        # 应用 'Large.TMenubutton' 样式
        algo_menu = ttk.OptionMenu(ctrl_frame, self.algorithm_var, "边缘", "边缘", "扫描线", style='Large.TMenubutton')
        # --- 修改2: 将右侧间距从 12 增加到 30，以隔开按钮 ---
        algo_menu.pack(side=tk.LEFT, padx=(4, 30))

        # 应用 'Large.TButton' 样式
        self.start_btn = ttk.Button(ctrl_frame, text="开始绘画", command=self.start_drawing, style='Large.TButton')
        self.start_btn.pack(side=tk.LEFT)

        # Log area
        log_frame = ttk.LabelFrame(left_frame, text="日志 / 提示")
        log_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=(0,6))
        self.log_text = tk.Text(log_frame, height=10, wrap=tk.WORD)
        # Make the text widget read-only for the user; program will enable/disable when appending
        self.log_text.configure(state=tk.DISABLED)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        log_scroll = ttk.Scrollbar(log_frame, command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text['yscrollcommand'] = log_scroll.set

        # Register print_utils GUI callback so console-style messages also
        # appear inside the GUI log. Use a thread-safe proxy (after) because
        # print_utils may call the callback from background threads.
        try:
            from utils import print_utils as print_utils

            def _gui_log_proxy(msg: str) -> None:
                # schedule append_log on the main thread
                try:
                    self.log_text.after(0, lambda m=msg: self.append_log(m))
                except Exception:
                    # If scheduling fails, fallback to direct append (best-effort)
                    try:
                        self.append_log(msg)
                    except Exception:
                        pass

            print_utils.register_gui_logger(_gui_log_proxy)
        except Exception:
            # ignore registration errors; console output still works
            pass

        # Right: config panel
        cfg_label = ttk.Label(right_frame, text="当前配置", font=("Arial", 12, 'bold'))
        cfg_label.pack(anchor=tk.NW, padx=6, pady=6)

        cfg_canvas = tk.Canvas(right_frame, width=200)
        cfg_scroll = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=cfg_canvas.yview)
        cfg_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        cfg_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        cfg_canvas.configure(yscrollcommand=cfg_scroll.set)

        self.cfg_inner = ttk.Frame(cfg_canvas)
        cfg_canvas.create_window((0,0), window=self.cfg_inner, anchor='nw')
        self.cfg_inner.bind('<Configure>', lambda e: cfg_canvas.configure(scrollregion=cfg_canvas.bbox('all')))

        self._render_config_panel()

    def _on_canvas_resize(self, event):
        # Re-center image when canvas size changes
        self._draw_image_on_canvas()

    def _draw_image_on_canvas(self):
        self.canvas.delete('all')
        
        # 1. 检查是否有 PIL 图像对象
        if self.image_pil is None:
            return

        # 2. 获取画布的当前实际尺寸
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()

        # 3. 如果画布还未绘制 (尺寸为1)，则不执行任何操作
        if canvas_w <= 1 or canvas_h <= 1:
            return
            
        # 4. (自适应) 复制原始 PIL 图像并按比例缩放
        #    使其适应画布大小，同时保持纵横比
        img_copy = self.image_pil.copy()
        
        #    thumbnail 会在原地修改 img_copy，使其缩小到适应 (canvas_w, canvas_h)
        #    Image.LANCZOS 是高质量的缩放算法
        img_copy.thumbnail((canvas_w, canvas_h), Image.LANCZOS)
        
        # 5. 将 *缩放后* 的图像转换为 Tkinter PhotoImage
        #    这一步必须在绘制函数中完成，而不是在 open_file 中
        self.image_tk = ImageTk.PhotoImage(img_copy)

        # 6. (居中) 计算画布的中心点
        cx = canvas_w / 2
        cy = canvas_h / 2
        
        # 7. 在中心点 (cx, cy) 创建图像，并使用 'center' 锚点
        self.canvas.create_image(cx, cy, image=self.image_tk, anchor=tk.CENTER)

        # 备注: 既然图片已经自适应了，就不再需要设置 scrollregion 了
        # self.canvas.config(scrollregion=(0,0,w,h)) # 这行可以删除

    def open_file(self):
        file_path = filedialog.askopenfilename(initialdir=os.path.join(os.getcwd(), 'pic'),
                                               filetypes=[('Image files', '*.png;*.jpg;*.jpeg;*.bmp;*.gif'), ('All files', '*.*')])
        if not file_path:
            return
        try:
            pil = Image.open(file_path)
            self.image_pil = pil
            # self.image_tk = ImageTk.PhotoImage(pil)
            self.image_path = file_path
            self.append_log(f"已打开图片: {file_path}")
            self._draw_image_on_canvas()
        except Exception as e:
            messagebox.showerror("打开失败", f"无法打开图片: {e}")

    def start_drawing(self):
        if not self.image_path:
            messagebox.showwarning("未选择图片", "请先通过 文件 -> 打开文件 选择图片。")
            return

        algo = self.algorithm_var.get()
        self.append_log(f"开始绘画 - 算法: {algo}")
        # Disable start button while drawing
        self.start_btn.config(state=tk.DISABLED)

        def run_draw():
            try:
                if algo == '边缘':
                    drawer = AutoDrawerCanny(self.config_data)
                    drawer.run(self.image_path)
                else:
                    drawer = AutoDrawerScan(self.config_data)
                    drawer.run(self.image_path)
                self.append_log("绘画完成")
            except Exception as e:
                self.append_log(f"绘画出错: {e}")
            finally:
                self.start_btn.config(state=tk.NORMAL)

        t = threading.Thread(target=run_draw, daemon=True)
        t.start()

    def append_log(self, text):
        # Temporarily enable the widget, insert, then disable to prevent user edits
        try:
            self.log_text.configure(state=tk.NORMAL)
            self.log_text.insert(tk.END, text + '\n')
            self.log_text.see(tk.END)
        finally:
            try:
                self.log_text.configure(state=tk.DISABLED)
            except Exception:
                pass

    def _render_config_panel(self):
        # Clear
        for child in self.cfg_inner.winfo_children():
            child.destroy()

        row = 0
        for section, params in self.config_data.items():
            lbl = ttk.Label(self.cfg_inner, text=section, font=("Arial", 10, 'bold'))
            lbl.grid(row=row, column=0, sticky='w', padx=4, pady=(6,2))
            row += 1
            for k, v in params.items():
                key_lbl = ttk.Label(self.cfg_inner, text=f"{k}:")
                val_lbl = ttk.Label(self.cfg_inner, text=str(v))
                key_lbl.grid(row=row, column=0, sticky='w', padx=8)
                val_lbl.grid(row=row, column=1, sticky='w', padx=8)
                row += 1

        # refresh button
        ttk.Button(self.cfg_inner, text="刷新", command=self.refresh_config).grid(row=row, column=0, pady=8, padx=6, sticky='w')

    def refresh_config(self):
        self.config_data = load_config()
        self._render_config_panel()
        self.append_log("配置已刷新")

    def open_modify_config(self):
        # Simple editor: show sections and keys with entries
        top = tk.Toplevel(self)
        top.title("修改当前配置")
        # 设定一个最小尺寸
        top.minsize(300, 400) 

        frm = ttk.Frame(top)
        frm.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        canvas = tk.Canvas(frm)
        sb = ttk.Scrollbar(frm, orient=tk.VERTICAL, command=canvas.yview)
        inner = ttk.Frame(canvas)
        
        canvas.create_window((0,0), window=inner, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        # --- 解决方案 1: 修复滚动条 ---
        # 绑定 inner 框架的 Configure 事件，以便在内容变化时更新 canvas 的滚动区域
        inner.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
        # --- 滚动条修复结束 ---

        entries = {}
        r = 0
        for section, params in self.config_data.items():
            ttk.Label(inner, text=section, font=("Arial", 10, 'bold')).grid(row=r, column=0, columnspan=2, sticky='w', pady=(6,2), padx=4)
            r += 1
            for k, v in params.items():
                ttk.Label(inner, text=k).grid(row=r, column=0, sticky='w', padx=8)

                # --- 解决方案 2: 替换为下拉框 ---
                widget = None
                
                # 检查值的类型是否为布尔型
                if isinstance(v, bool):
                    # 如果是 True/False，创建 Combobox (下拉框)
                    current_val = str(v) # "True" 或 "False"
                    # state="readonly" 阻止用户手动输入
                    cb = ttk.Combobox(inner, values=["True", "False"], state="readonly") 
                    cb.set(current_val)
                    cb.grid(row=r, column=1, sticky='we', padx=6, pady=2)
                    widget = cb # 将 combobox 存入
                else:
                    # 否则 (数字、字符串等)，创建原来的 Entry (输入框)
                    ent = ttk.Entry(inner)
                    ent.insert(0, str(v))
                    ent.grid(row=r, column=1, sticky='we', padx=6, pady=2)
                    widget = ent # 将 entry 存入
                
                # 使用通用变量 widget 存入字典
                entries[(section, k)] = widget
                # --- 下拉框替换结束 ---
                
                r += 1

        # --- !! 已删除重复的 canvas, sb, inner 和 for 循环代码 !! ---

        def save_and_close():
            # 尝试转换值
            for (section, key), widget in entries.items():
                # .get() 方法对 Entry 和 Combobox 都有效
                raw = widget.get()
                try:
                    # eval() 可以安全地将 "True" -> True, "50" -> 50
                    val = eval(raw)
                except Exception:
                    # 如果 eval 失败 (比如普通字符串)，则保留原始字符串
                    val = raw
                self.config_data[section][key] = val
                
            save_config(self.config_data)
            self.append_log("配置已保存")
            self._render_config_panel()
            top.destroy()

        # --- !! 解决方案 3: 修复按钮缩进 !! ---
        # 将按钮创建代码移到 save_and_close 函数 *外部*
        btn_row = ttk.Frame(top)
        btn_row.pack(fill=tk.X, padx=6, pady=6)
        ttk.Button(btn_row, text="保存", command=save_and_close).pack(side=tk.RIGHT)

    # --- 新增: 显示帮助图片的方法 ---
    def show_help_image(self):
        # 假设帮助图片在 'pic/help.png'
        help_image_path = os.path.join(os.getcwd(), 'pic', 'help.png') 
        
        if not os.path.exists(help_image_path):
            messagebox.showerror("帮助文件丢失", "未找到 'pic/help.png' 文件。")
            self.append_log("错误: 未找到 'pic/help.png'")
            return
            
        try:
            top = tk.Toplevel(self)
            top.title("帮助说明")
            
            pil_img = Image.open(help_image_path)
            img_tk = ImageTk.PhotoImage(pil_img)
            
            lbl = tk.Label(top, image=img_tk)
            lbl.image = img_tk # 关键: 保持对图片对象的引用，防止被垃圾回收
            lbl.pack()
            
            top.resizable(False, False) # 不允许调整窗口大小
            
        except Exception as e:
            messagebox.showerror("打开帮助失败", f"无法打开帮助图片: {e}")
            self.append_log(f"错误: 打开帮助图片失败 {e}")
    # --- 帮助方法结束 ---

    def reselect_board(self):
        self.append_log("开始重新选择画板区域，请根据提示操作...")

        def do_capture():
            try:
                X_A, Y_A, W, H = capture_screen_region("config/config.py")
                # update config
                if 'screen_config' not in self.config_data:
                    self.config_data['screen_config'] = {}
                self.config_data['screen_config'].update({'X_A': X_A, 'Y_A': Y_A, 'W': W, 'H': H})
                save_config(self.config_data)
                self.append_log(f"画板坐标已更新: ({X_A}, {Y_A}), 尺寸 {W}×{H}")
                self._render_config_panel()
            except Exception as e:
                self.append_log(f"重选画板失败: {e}")

        t = threading.Thread(target=do_capture, daemon=True)
        t.start()

    def reset_config_action(self):
        """Reset config to defaults while preserving special keys, with confirmation."""
        if not messagebox.askyesno("确认重置", "是否要将配置重置为默认值？\n（将保留 H_IMG、W_IMG、THRESHOLD_VALUE 与 screen_config）"):
            return

        def do_reset():
            try:
                reset_config_file()
                # reload into GUI
                self.config_data = load_config()
                self._render_config_panel()
                self.append_log("配置已重置为默认（保留指定项）并已刷新")
            except Exception as e:
                self.append_log(f"重置配置失败: {e}")

        t = threading.Thread(target=do_reset, daemon=True)
        t.start()


def main():
    app = HeyTeaGUI()
    app.mainloop()


if __name__ == '__main__':
    main()
