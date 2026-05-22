import os
import sys
import logging
from ..common import CURRENT_DIR

def build_llamacpp_command(config, executable_path, version):
    """
    根據配置字典構建 llama.cpp 執行命令。
    config: 預設集中的 config 字典
    executable_path: llamacpp 可執行文件路徑
    version: llamacpp 版本號 (int)
    """
    model_path = config.get("model_path", "")
    model_name = os.path.basename(model_path)
    
    option_model = ["--model", model_path]
    option_extra = []

    option_extra += [
        "-c", str(config.get("context_length", 2048)),
        "-ngl", str(config.get("gpu_layers", 200)),
    ]

    executable = os.path.basename(executable_path).replace(".exe", "")

    if executable == "llama-server":
        option_extra += [
            "-a", model_name,
            "--host", config.get("host", "127.0.0.1"),
            "--port", str(config.get("port", "8080")),
            "-np", str(config.get("n_parallel", 1)),
        ]
        option_extra.append("--metrics")

        if version is not None and version >= 3898:
            option_extra.append("--slots")
    elif executable == "llama-batched-bench":
        option_extra += [
            "-npp", config.get("npp", "768"),
            "-ntg", config.get("ntg", "384"),
            "-npl", config.get("npl", "1,2,4,8,16"),
        ]

    if config.get("flash_attention", True):
        option_extra.append("-fa")
        if version and version >= 6325:
            option_extra.append("on")
            
    if config.get("no_mmap", True):
        option_extra.append("--no-mmap")

    command = []
    command_template = config.get("command_template", config.get("custom_command", "%cmd%")).strip()
    if not command_template:
        command_template = "%cmd%"
        
    # 處理舊版預設集的兼容性
    if "%cmd%" not in command_template and "%cmd_raw%" not in command_template:
        if config.get("custom_command"):
             command_template = "%cmd_raw% " + config.get("custom_command")
        elif config.get("custom_command_append"):
             command_template = "%cmd% " + config.get("custom_command_append")
        else:
             command_template = "%cmd%"

    for command_part in command_template.split(" "):
        command_part = command_part.strip()
        if command_part == "%cmd%":
            command.append(executable_path)
            command += option_model
            command += option_extra
        elif command_part == "%cmd_raw%":
            command.append(executable_path)
            command += option_model
        elif command_part:
            command.append(command_part)
            
    return command
