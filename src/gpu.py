import os
import platform
import math
import logging
import subprocess
import json
from typing import List, Dict

from .sakura import SAKURA_LIST
from .utils import BytesToGiB
from .utils.gpu import GPUAbility, GPUType, GPUInfo
from .utils.gpu.nvidia import get_nvidia_gpus
from .sakura import SakuraCalculator
from .common import DEBUG_BUILD


class GPUDisplayHelper:
    """GPU顯示名稱處理助手類"""
    
    @staticmethod
    def create_display_name(gpu_info: GPUInfo, index: int) -> str:
        """創建GPU的顯示名稱"""
        return f"{gpu_info.name} (GPU {index})" if gpu_info.pci_bus_id else gpu_info.name
    
    @staticmethod
    def parse_display_name(display_name: str) -> tuple[str, int|None]:
        """解析GPU顯示名稱，返回(gpu_name, index)"""
        if " (GPU " in display_name and ")" in display_name:
            name_part, index_part = display_name.split(" (GPU ")
            try:
                index = int(index_part.rstrip(")"))
                return name_part, index
            except ValueError:
                return display_name, None
        return display_name, None
    
    @staticmethod
    def find_gpu_key(display_name: str, gpu_info_map: Dict[str, GPUInfo]) -> str|None:
        """根據顯示名稱找到對應的GPU key"""
        # 如果顯示名稱本身就是key
        if display_name in gpu_info_map:
            return display_name
            
        # 嘗試解析顯示名稱
        gpu_name, gpu_index = GPUDisplayHelper.parse_display_name(display_name)
        
        # 在gpu_info_map中查找匹配的GPU
        matching_keys = []
        for key, info in gpu_info_map.items():
            if info.name == gpu_name:
                matching_keys.append(key)
        
        # 如果找到多個匹配的GPU，使用索引選擇
        if matching_keys:
            if gpu_index is not None and gpu_index < len(matching_keys):
                return matching_keys[gpu_index]
            # 如果沒有索引或索引無效，返回第一個匹配的
            return matching_keys[0]
        
        return None
    
    @staticmethod
    def match_gpu_name(display_name: str, target_name: str) -> bool:
        """檢查目標名稱是否匹配顯示名稱"""
        gpu_name, _ = GPUDisplayHelper.parse_display_name(display_name)
        return target_name in gpu_name

class GPUManager:
    def __init__(self):
        self.gpu_info_map: Dict[str, GPUInfo] = {}
        self.nvidia_gpus = []
        self.amd_gpus = []
        self.intel_gpus = []
        if DEBUG_BUILD:
            logging.info("GPU管理器初始化 (DEBUG模式)")
        self.detect_gpus()

    @staticmethod
    def get_gpu_index_from_pci(pci_bus_id: str) -> int:
        """從 PCI 總線 ID 中提取設備號作為 GPU 索引"""
        try:
            # PCI 總線 ID 格式為 "00000000:01:00.0"，我們提取設備號（01）作為索引
            if pci_bus_id and ":" in pci_bus_id:
                device_id = pci_bus_id.split(":")[1]
                index = int(device_id, 16)  # 將十六進位設備號轉換為十進位
                if DEBUG_BUILD:
                    logging.debug(f"從PCI總線ID '{pci_bus_id}' 提取設備號: {index}")
                return index
        except (IndexError, ValueError) as e:
            logging.warning(f"無法從PCI總線ID提取設備號: {pci_bus_id}, 錯誤: {e}")
        return 0

    def __add_gpu_to_list(self, gpu_info: GPUInfo):
        if gpu_info.gpu_type == GPUType.NVIDIA:
            # 直接從 PCI 總線 ID 獲取 GPU 索引
            gpu_index = self.get_gpu_index_from_pci(gpu_info.pci_bus_id) if gpu_info.pci_bus_id else len(self.nvidia_gpus)
            display_name = GPUDisplayHelper.create_display_name(gpu_info, gpu_index)
            self.nvidia_gpus.append(display_name)
            if DEBUG_BUILD:
                logging.debug(f"添加NVIDIA GPU到清單: {display_name}, 索引: {gpu_index}, PCI總線ID: {gpu_info.pci_bus_id}")
        elif gpu_info.gpu_type == GPUType.AMD:
            self.amd_gpus.append(gpu_info.name)
            if DEBUG_BUILD:
                logging.debug(f"添加AMD GPU到清單: {gpu_info.name}")
        elif gpu_info.gpu_type == GPUType.INTEL:
            self.intel_gpus.append(gpu_info.name)
            if DEBUG_BUILD:
                logging.debug(f"添加Intel GPU到清單: {gpu_info.name}")

    def __universal_detect_nvidia_gpu(self):
        ''' Detect NVIDIA GPUs using nvidia-smi '''
        if DEBUG_BUILD:
            logging.debug("開始檢測NVIDIA GPU (通用方法)")
        self.nvidia_gpus = []
        nvidia_gpu_info = get_nvidia_gpus()
        
        if DEBUG_BUILD and nvidia_gpu_info:
            logging.debug(f"檢測到 {len(nvidia_gpu_info)} 個NVIDIA GPU")
        
        # 處理每個 GPU
        for gpu_info in nvidia_gpu_info:
            # 使用 pci_bus_id 作為唯一標識符
            gpu_key = gpu_info.pci_bus_id if gpu_info.pci_bus_id else gpu_info.name
            # 直接從 PCI 總線 ID 獲取 GPU 索引
            gpu_index = self.get_gpu_index_from_pci(gpu_info.pci_bus_id) if gpu_info.pci_bus_id else len(self.nvidia_gpus)
            display_name = GPUDisplayHelper.create_display_name(gpu_info, gpu_index)
            self.nvidia_gpus.append(display_name)
            
            if DEBUG_BUILD:
                gpu_mem_gib = BytesToGiB(gpu_info.dedicated_gpu_memory) if gpu_info.dedicated_gpu_memory else 0
                avail_mem_gib = BytesToGiB(gpu_info.avail_dedicated_gpu_memory) if gpu_info.avail_dedicated_gpu_memory else 0
                logging.debug(f"NVIDIA GPU詳情: 名稱={gpu_info.name}, 索引={gpu_index}, PCI={gpu_info.pci_bus_id}, "
                             f"總顯存={gpu_mem_gib:.2f}GiB, 可用顯存={avail_mem_gib:.2f}GiB")
            
            if gpu_key in self.gpu_info_map:
                self.gpu_info_map[gpu_key].merge_from(gpu_info)
                logging.info(f"更新 GPU 資訊: {self.gpu_info_map[gpu_key]}")
            else:
                logging.info(f"檢測到新的NVIDIA GPU: {gpu_info}")
                self.gpu_info_map[gpu_key] = gpu_info

    def detect_gpus(self):
        ''' platform-specific method to detect GPUs  '''
        if DEBUG_BUILD:
            logging.debug(f"開始檢測GPU, 平臺: {platform.system()}")
            
        if platform.system() == "Windows":
            self.detect_gpus_windows()
        elif platform.system() == "Linux":
            self.detect_gpus_linux()
        else:
            logging.warning("Disable GPU detection on non-windows platform")
            
        if DEBUG_BUILD:
            logging.debug(f"GPU檢測完成, 共檢測到: {len(self.nvidia_gpus)} 個NVIDIA GPU, "
                         f"{len(self.amd_gpus)} 個AMD GPU, {len(self.intel_gpus)} 個Intel GPU")
            logging.debug(f"GPU資訊映射表: {json.dumps({k: str(v.__dict__) for k, v in self.gpu_info_map.items()}, indent=2)}")

    def detect_gpus_linux(self):
        if DEBUG_BUILD:
            logging.debug("在Linux平臺上檢測GPU")
        self.__universal_detect_nvidia_gpu()
        return

    def detect_gpus_windows(self):
        if DEBUG_BUILD:
            logging.debug("在Windows平臺上檢測GPU")
            
        # Non stable gpu detection
        try:
            # Detect gpu properties
            from .utils import windows
            adapter_values = windows.get_gpu_mem_info()
            
            if DEBUG_BUILD:
                logging.debug(f"從Windows註冊表檢測到 {len(adapter_values)} 個GPU適配器")
                for i, adapter in enumerate(adapter_values):
                    mem_gib = BytesToGiB(adapter.MemorySize)
                    logging.debug(f"適配器 {i}: 名稱={adapter.AdapterString}, 顯存={mem_gib:.2f}GiB, PCI={adapter.pci_bus_id}")

            for adapter in adapter_values:
                name = adapter.AdapterString
                gpu_type = self.get_gpu_type(name)

                dedicated_gpu_memory = adapter.MemorySize
                # 使用 pci_bus_id 作為唯一標識符
                gpu_key = adapter.pci_bus_id if hasattr(adapter, 'pci_bus_id') else name
                if gpu_key not in self.gpu_info_map:
                    gpu_info = GPUInfo(
                        index=None,
                        name=name,
                        gpu_type=gpu_type,
                        dedicated_gpu_memory=dedicated_gpu_memory,
                        pci_bus_id=adapter.pci_bus_id if hasattr(adapter, 'pci_bus_id') else None
                    )
                    logging.info(f"檢測到 GPU: {gpu_info}")
                    self.__add_gpu_to_list(gpu_info)
                    self.gpu_info_map[gpu_key] = gpu_info
                else:
                    logging.warning(f"重複的 GPU: {gpu_key}, 已存在，忽略")

        except Exception as e:
            logging.warning(f"detect_gpus_properties() 出錯: {str(e)}")
            if DEBUG_BUILD:
                import traceback
                logging.debug(f"GPU屬性檢測異常詳情: {traceback.format_exc()}")

        # 檢測NVIDIA GPU
        self.__universal_detect_nvidia_gpu()

        # 檢測AMD GPU
        try:
            import wmi

            c = wmi.WMI()
            amd_gpus_temp = []
            for gpu in c.Win32_VideoController():
                if "AMD" in gpu.Name or "ATI" in gpu.Name:
                    amd_gpus_temp.append(gpu.Name)
                    if DEBUG_BUILD:
                        logging.debug(f"從WMI檢測到AMD GPU: {gpu.Name}, 驅動版本: {gpu.DriverVersion}, 狀態: {gpu.Status}")
            logging.info(f"檢測到AMD GPU(正向清單): {amd_gpus_temp}")
            # 反向添加AMD GPU
            self.amd_gpus = list(reversed(amd_gpus_temp))
            logging.info(f"檢測到AMD GPU(反向清單): {self.amd_gpus}")
        except Exception as e:
            logging.error(f"檢測AMD GPU時出錯: {str(e)}")
            if DEBUG_BUILD:
                import traceback
                logging.debug(f"AMD GPU檢測異常詳情: {traceback.format_exc()}")

    def get_gpu_type(self, gpu_name):
        if "NVIDIA" in gpu_name.upper():
            return GPUType.NVIDIA
        elif "AMD" in gpu_name.upper() or "ATI" in gpu_name.upper():
            return GPUType.AMD
        # TODO(kuriko): add intel gpu support in future
        else:
            return GPUType.UNKNOWN

    def check_gpu_ability(self, gpu_display_name: str, model_name: str, context_length: int = None, n_parallel: int = None) -> GPUAbility:
        if DEBUG_BUILD:
            logging.debug(f"檢查GPU能力: 顯示名稱={gpu_display_name}, 模型={model_name}, "
                         f"上下文長度={context_length}, 並行數={n_parallel}")
            
        # 從顯示名稱中找到對應的GPU key
        gpu_key = GPUDisplayHelper.find_gpu_key(gpu_display_name, self.gpu_info_map)
        if not gpu_key or gpu_key not in self.gpu_info_map:
            logging.error(f"未找到GPU: {gpu_display_name}, 當前已知GPU: {list(self.gpu_info_map.keys())}")
            return GPUAbility(is_capable=False, reason=f"未找到顯卡對應的參數資訊")

        gpu_info = self.gpu_info_map[gpu_key]
        if DEBUG_BUILD:
            logging.debug(f"找到匹配的GPU: {gpu_key}, 類型: {gpu_info.gpu_type}, "
                         f"總顯存: {BytesToGiB(gpu_info.dedicated_gpu_memory):.2f}GiB")
            
        if gpu_info.gpu_type not in [GPUType.NVIDIA, GPUType.AMD]:
            return GPUAbility(
                is_capable=False, reason=f"目前只支援 NVIDIA 和 AMD 的顯卡"
            )

        if gpu_info.avail_dedicated_gpu_memory is not None:
            ability = self._check_dynamic_memory(gpu_info, model_name, context_length, n_parallel)
        else:
            ability = self._check_static_memory(gpu_info, model_name)

        gpu_info.ability = ability
        
        if DEBUG_BUILD:
            logging.debug(f"GPU能力檢查結果: 是否可用={ability.is_capable}, 原因={ability.reason}")
            
        return ability

    def _check_dynamic_memory(self, gpu_info: GPUInfo, model_name: str, context_length: int = None, n_parallel: int = None) -> GPUAbility:
        """檢查動態可用顯存"""
        gpu_mem = gpu_info.avail_dedicated_gpu_memory
        gpu_mem_gib = BytesToGiB(gpu_mem)
        total_mem_gib = BytesToGiB(gpu_info.dedicated_gpu_memory)
        
        if DEBUG_BUILD:
            logging.debug(f"動態顯存檢查: 可用={gpu_mem_gib:.2f}GiB, 總顯存={total_mem_gib:.2f}GiB")
        
        model = SAKURA_LIST[model_name]
        if not model:
            if DEBUG_BUILD:
                logging.debug(f"未找到模型 {model_name} 的配置資訊，預設允許運行")
            return GPUAbility(is_capable=True, reason="")
            
        try:
            calculator = SakuraCalculator(model)
            if context_length is None or n_parallel is None:
                # 如果沒有提供參數，使用推薦配置
                config = calculator.recommend_config(gpu_mem_gib)
                if DEBUG_BUILD:
                    logging.debug(f"使用推薦配置: 上下文長度={config['context_length']}, 並行數={config['n_parallel']}")
            else:
                config = {
                    "context_length": context_length,
                    "n_parallel": n_parallel
                }
                if DEBUG_BUILD:
                    logging.debug(f"使用指定配置: 上下文長度={context_length}, 並行數={n_parallel}")
                
            # 計算實際顯存使用
            memory_usage = calculator.calculate_memory_requirements(
                config["context_length"]
            )
            
            if DEBUG_BUILD:
                logging.debug(f"顯存需求計算結果: 總需求={memory_usage['total_size_gib']:.2f}GiB, "
                             f"模型大小={memory_usage['model_size_gib']:.2f}GiB, "
                             f"KV緩存={memory_usage['kv_cache_size_gib']:.2f}GiB")
            
            if gpu_mem_gib < memory_usage['total_size_gib']:
                return GPUAbility(
                    is_capable=False,
                    reason=f"顯卡 {gpu_info.name} 的顯存不足\n"
                    f"預計需要 {memory_usage['total_size_gib']:.2f} GiB 顯存\n"
                    f"當前系統只有 {gpu_mem_gib:.2f} GiB 剩餘顯存\n"
                    f"總顯存: {total_mem_gib:.2f} GiB"
                )
        except Exception as e:
            logging.warning(f"顯存需求計算失敗: {e}")
            if DEBUG_BUILD:
                import traceback
                logging.debug(f"顯存計算異常詳情: {traceback.format_exc()}")
                
            # 如果計算失敗，回退到基本顯存檢查
            if (gpu_mem_req_gib := model.minimal_gpu_memory_gib) != 0 \
            and gpu_mem_gib < gpu_mem_req_gib:
                return GPUAbility(
                    is_capable=False,
                    reason=f"顯卡 {gpu_info.name} 的顯存不足\n"
                    f"至少需要 {gpu_mem_req_gib:.2f} GiB 顯存\n"
                    f"當前系統只有 {gpu_mem_gib:.2f} GiB 剩餘顯存"
                )
        
        return GPUAbility(is_capable=True, reason="")

    def _check_static_memory(self, gpu_info: GPUInfo, model_name: str) -> GPUAbility:
        """檢查靜態總顯存"""
        gpu_mem = gpu_info.dedicated_gpu_memory
        gpu_mem_gib = math.ceil(BytesToGiB(gpu_mem)) \
            if gpu_mem > (2**30) else BytesToGiB(gpu_mem)
        
        if DEBUG_BUILD:
            logging.debug(f"靜態顯存檢查: 總顯存={gpu_mem_gib:.2f}GiB")
        
        model = SAKURA_LIST[model_name]
        if (
            model
            and (gpu_mem_req_gib := model.minimal_gpu_memory_gib) != 0
            and gpu_mem_gib < gpu_mem_req_gib
        ):
            return GPUAbility(
                is_capable=False,
                reason=f"顯卡 {gpu_info.name} 的顯存不足\n"
                f"至少需要 {gpu_mem_req_gib:.2f} GiB 顯存\n"
                f"當前顯卡總顯存為 {gpu_mem_gib:.2f} GiB"
            )
        
        return GPUAbility(is_capable=True, reason="")

    def set_gpu_env(self, env, selected_gpu_display_name, selected_index):
        if DEBUG_BUILD:
            logging.debug(f"設定GPU環境變量: 顯示名稱={selected_gpu_display_name}, 索引={selected_index}")
            
        # 從顯示名稱中找到對應的GPU key
        gpu_key = GPUDisplayHelper.find_gpu_key(selected_gpu_display_name, self.gpu_info_map)
        if not gpu_key:
            logging.warning(f"未找到GPU: {selected_gpu_display_name}")
            return env
            
        gpu_info = self.gpu_info_map[gpu_key]
        if gpu_info.gpu_type == GPUType.NVIDIA:
            env["CUDA_VISIBLE_DEVICES"] = str(selected_index)
            logging.info(f"設定 CUDA_VISIBLE_DEVICES = {env['CUDA_VISIBLE_DEVICES']}")
            if DEBUG_BUILD:
                logging.debug(f"為NVIDIA GPU設定環境變量: CUDA_VISIBLE_DEVICES={selected_index}")
        elif gpu_info.gpu_type == GPUType.AMD:
            env["HIP_VISIBLE_DEVICES"] = str((selected_index) - len(self.nvidia_gpus))
            logging.info(f"設定 HIP_VISIBLE_DEVICES = {env['HIP_VISIBLE_DEVICES']}")
            if DEBUG_BUILD:
                logging.debug(f"為AMD GPU設定環境變量: HIP_VISIBLE_DEVICES={env['HIP_VISIBLE_DEVICES']}")
        else:
            logging.warning(f"未知的GPU類型: {selected_gpu_display_name}")
        return env
