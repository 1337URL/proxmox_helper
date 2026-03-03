from proxmoxer import ProxmoxAPI
from time import sleep
from typing import Literal, List
from pathlib import PurePosixPath
from multiprocessing.pool import ThreadPool
from threading import Thread
import base64


class proxmox_helper(ProxmoxAPI):
    def __init__(self, host=None, backend="https", service="PVE", **kwargs) -> None:
        super().__init__(host, backend, service, **kwargs)

    def get_nodes(self) -> list:
        data: list = self.nodes.get() or []
        return list(map(lambda x: x["node"], data))
    
    def get_networks(self, node: str, types: list = ["any_bridge"], full: bool = False) -> list:
        data: list = self.nodes(node).network.get(type= ",".join(types)) or []
        if full:
            return data
        return list(map(lambda x: x["iface"], data))
    
    def get_network(self, node: str, iface: str) -> dict:
        return self.nodes(node).network(iface).get() or {}

    def delete_networks(self, node: str, ifaces: list) -> None:
        for iface in ifaces:
            self.nodes(node).network(iface).delete()

    def create_network(self, node: str, **kwargs) -> None:
        self.nodes(node).network.post(**kwargs)

    def edit_network(self, node: str, iface: str, **kwargs) -> None:
        self.nodes(node).network(iface).put(**kwargs)

    def update_networks(self, node: str) -> None:
        self.nodes(node).network.put()

    def get_state_network(self, node: str, iface: str) -> Literal["running", "stopped", "absent"]:
        networks = self.get_networks(node, full= True)
        for network in networks:
            if network.get("iface") == iface:
                return "running" if network.get("active") == 1 else "stopped"
        return "absent"
    
    def ensure_state_network(self,
                                 node: str, 
                                 iface: str, 
                                 state: List[Literal["running", "stopped", "absent"]], 
                                 poll_timeout: int | float = 1, 
                                 poll_attempts: int = 10
                                 ) -> bool: # stopped can mean pending witch acts like absent
        while not self.get_state_network(node, iface) in state:
            if poll_attempts == 0:
                return False
            poll_attempts -= 1
            sleep(poll_timeout)
        return True
    
    def vm_name_to_id(self, node, name) -> int:
        vmid = self.get_qemu_vms(node).get(name)
        if not vmid:
            raise Exception(f"VM named {name} does not exist.")
        return vmid

    def get_qemu_vms(self, node: str) -> dict:
        data: list = self.nodes(node).qemu.get() or []
        return dict([(vm["name"], vm["vmid"]) for vm in data if "vmid" in vm and "name" in vm])
    
    def get_config_qemu_vm(self, node: str, name: str, **kwargs) -> dict:
        vmid = self.vm_name_to_id(node, name)
        return self.get_config_qemu_vm_id(node, vmid, **kwargs)
    
    def get_config_qemu_vm_id(self, node: str, vmid: int, **kwargs) -> dict:
        return self.nodes(node).qemu(vmid).config.get(**kwargs) or {}
    
    def get_ip_qemu_vm(self, node: str, name: str, mac: str) -> str|None:
        vmid = self.vm_name_to_id(node, name)
        return self.get_ip_qemu_vm_id(node, vmid, mac)

    def get_ip_qemu_vm_id(self, node: str, vmid: int, mac: str) -> str|None:
        self.wait_for_qemu_agent_id(node, vmid)
        output = self.run_commands_vm_id(node, vmid, [f"printf \"%s\" $((ip -4 -o address show dev $(ip -o link show | grep -i {mac} | awk '{{print $2}}' | cut -d: -f1) 2> /dev/null || exit ) | awk '{{print $4}}' | cut -d/ -f1)"])
        return output.get("out-data")

    def delete_qemu_vms(self, 
                        node: str, 
                        names: list, 
                        auto_stop: bool = True, 
                        overrule_shutdown: int = 1,
                        timeout: int = 0, 
                        destroy_unreferenced_disks: bool = True, 
                        purge: bool = True,
                        poll_timeout: int | float = 1, 
                        poll_attempts: int = 10
                        ) -> None:
        data = self.get_qemu_vms(node)
        vmids = [data[name] for name in names]
        self.delete_qemu_vms_id(node, vmids, auto_stop, overrule_shutdown, timeout, destroy_unreferenced_disks, purge, poll_timeout, poll_attempts)

    def delete_qemu_vms_id(self, 
                           node: str, 
                           ids: list, 
                           auto_stop: bool = True, 
                           overrule_shutdown: int = 1,
                           timeout: int = 0, 
                           destroy_unreferenced_disks: bool = True, 
                           purge: bool = True,
                           poll_timeout: int | float = 1, 
                           poll_attempts: int = 10
                           ) -> None:
        payload = f"?destroy-unreferenced-disks={int(destroy_unreferenced_disks)}&purge={int(purge)}"
        for vmid in ids:
            if auto_stop:
                self.stop_qemu_vm_id(node, vmid, overrule_shutdown, timeout= timeout)
                self.ensure_state_qemu_vm_id(node, vmid, ["stopped"], poll_timeout, poll_attempts)
            self.nodes(node).qemu(vmid).delete(payload)

    def create_qemu_vm(self, 
                       node: str,
                       unique: bool = True,
                       **kwargs
                       ) -> None:
        if unique and kwargs.get("name") in self.get_qemu_vms(node).keys():
            raise Exception(f"Name {kwargs.get("name")} is not unique")
        if not kwargs.get("vmid"):
            kwargs["vmid"] = self.get_next_vmid()
        self.nodes(node).qemu.post(**kwargs)
        self.get_qemu_vms(node) # bugfix make qemu realize the new vms
        

    def edit_qemu_vm(self, node: str, name: str, **kwargs) -> None:
        vmid = self.vm_name_to_id(node, name)
        self.edit_qemu_vm_id(node, vmid, **kwargs)

    def edit_qemu_vm_id(self, node: str, vmid: int, **kwargs) -> None:
        self.nodes(node).qemu(vmid).config.post(**kwargs)

    def start_qemu_vm(self, node: str, name: str, **kwargs) -> None:
        vmid = self.vm_name_to_id(node, name)
        self.start_qemu_vm_id(node, vmid, **kwargs)

    def start_qemu_vm_id(self, node: str, vmid: int, **kwargs) -> None:
        self.nodes(node).qemu(vmid).status.start.post(**kwargs)

    def stop_qemu_vm(self, 
                        node: str,
                        name: str, 
                        overrule_shutdown: int = 1, 
                        **kwargs
                        ) -> None:
        vmid = self.vm_name_to_id(node, name)
        self.stop_qemu_vm_id(node, vmid, overrule_shutdown, **kwargs)

    def stop_qemu_vm_id(self, 
                        node: str, 
                        vmid: int, 
                        overrule_shutdown: int = 1, 
                        **kwargs
                        ) -> None:
        kwargs["overrule-shutdown"] = overrule_shutdown
        self.nodes(node).qemu(vmid).status.stop.post(**kwargs)

    def reset_qemu_vm(self, node: str, name: str) -> None:
        vmid = self.vm_name_to_id(node, name)
        self.reset_qemu_vm_id(node, vmid)

    def reset_qemu_vm_id(self, node: str, vmid: int) -> None:
        self.nodes(node).qemu(vmid).status.reset.post()

    def get_state_qemu_vms(self, node: str) -> list:
        return self.nodes(node).qemu.get() or []
    
    def get_state_qemu_vm(self, node: str, name: str) -> Literal["running", "stopped", "absent"]:
        vmid = self.get_qemu_vms(node).get(name)
        if not vmid:
            return "absent"
        return self.get_state_qemu_vm_id(node, vmid)
    
    def get_state_qemu_vm_id(self, node: str, vmid: int) -> Literal["running", "stopped", "absent"]:
        vms = self.get_state_qemu_vms(node) or []
        vm = [vm["status"] for vm in vms if "vmid" in vm and vm["vmid"] == vmid]
        return vm[0] if len(vm) > 0 else "absent"
    
    def ensure_state_qemu_vm(self,
                                 node: str, 
                                 name: str, 
                                 state: List[Literal["running", "stopped", "absent"]], 
                                 poll_timeout: int | float = 1, 
                                 poll_attempts: int = 10
                                 ) -> bool:
        vmid = self.get_qemu_vms(node).get(name)
        if not vmid and "absent" in state:
            return True
        elif not vmid:
            raise Exception(f"VM named {name} does not exist.")
        return self.ensure_state_qemu_vm_id(node, vmid, state, poll_timeout, poll_attempts)

    def ensure_state_qemu_vm_id(self,
                                 node: str, 
                                 vmid: int, 
                                 state: List[Literal["running", "stopped", "absent"]], 
                                 poll_timeout: int | float = 1, 
                                 poll_attempts: int = 10
                                 ) -> bool:
        while not self.get_state_qemu_vm_id(node, vmid) in state:
            if poll_attempts == 0:
                return False
            poll_attempts -= 1
            sleep(poll_timeout)
        return True
    
    def wait_for_qemu_agent(self,
                            node: str, 
                            name: str, 
                            poll_timeout: int | float = 1, 
                            poll_attempts: int = 10
                            ) -> None:
        vmid = self.vm_name_to_id(node, name)
        self.wait_for_qemu_agent_id(node, vmid, poll_timeout, poll_attempts)
    
    def wait_for_qemu_agent_id(self,
                                 node: str, 
                                 vmid: int, 
                                 poll_timeout: int | float = 1, 
                                 poll_attempts: int = 10
                                 ) -> None:
        while True:
            if poll_attempts == 0:
                raise Exception(f"VM with id:{vmid} timed out while waiting for qemu agent.")
            try:
                self.nodes(node).qemu(vmid).agent.ping.post()
                return
            except Exception as e:
                if "500 Internal Server Error: QEMU guest agent is not running" != str(e):
                    raise e
            poll_attempts -= 1
            sleep(poll_timeout)
    
    def run_commands_vm(self, node: str, name: str, cmd: list, poll_timeout: int | float = 1, poll_attempts: int = 10) -> dict:
        vmid = self.vm_name_to_id(node, name)
        return self.run_commands_vm_id(node, vmid, cmd, poll_timeout, poll_attempts)
    
    def run_commands_vm_id(self, node: str, vmid: int, cmd: list, poll_timeout: int | float = 1, poll_attempts: int = 10) -> dict:
        resp = self.nodes(node).qemu(vmid).agent.exec.post(command=["bash", "-c", ";".join(cmd)])
        if not resp:
            e = Exception("Agent did not return a response. Cannot track execution.")
            e.add_note(f"Error occured while executing {cmd} on vm with id {vmid}.")
            raise e
        pid = resp["pid"] # API documentation says that pid is obligatory in response
        while True:
            if poll_attempts == 0:
                e = Exception("Command execution timed out")
                e.add_note(f"Error occured while executing {cmd} on vm with id {vmid}.")
                raise e
            result = self.nodes(node).qemu(vmid).agent("exec-status").get(pid=pid)
            if result and result.get("exited") == 1:
                return result
            poll_attempts -= 1
            sleep(poll_timeout)

    def write_file_to_vm(self, node: str, name: str, path: PurePosixPath | str, data: bytes | str) -> None:
        vmid = self.vm_name_to_id(node, name)
        self.write_file_to_vm_id(node, vmid, path, data)

    def write_file_to_vm_id(self, node: str, vmid: int, path: PurePosixPath | str, data: bytes | str) -> None:
        block_size = 40 * 1024
        path = str(PurePosixPath(path))
        if type(data) == bytes:
            data = base64.b64encode(data).decode('ascii')
        else:
            base64.b64decode(data, validate=True) # only used to validate the string
        if len(data) < block_size:
            self.nodes(node).qemu(vmid).agent("file-write").post(file= path, content= data, encode= 0)
            return
        filename = path.split("/")[-1]
        temp_path = f"/tmp/{filename}"
        data_parts = [data[i:i + block_size] for i in range(0, len(data), block_size)] # TODO improve this shit
        file_names = [temp_path + "." + str(file_num).zfill(4) for file_num in range(len(data_parts))]
        args = zip([node]*len(data_parts), [vmid]*len(data_parts), file_names, data_parts)
        with ThreadPool(10) as TP:
            TP.starmap(self._write_file_to_vm, args)
        self.run_commands_vm_id(node, vmid, [f"cat {temp_path}.* > {path} && rm {temp_path}.*"])

    def _write_file_to_vm(self, node: str, vmid: int, path: str, data: str) -> None:
        for _ in range(5):
            try:
                self.nodes(node).qemu(vmid).agent("file-write").post(file = path, content = data, encode = 0)
                return
            except Exception as e:
                print(e)
        raise Exception(f"Failed to transfer file part {path}")

    def read_file_from_vm(self, node: str, name: str, path: PurePosixPath | str) -> dict:
        vmid = self.vm_name_to_id(node, name)
        return self.read_file_from_vm_id(node, vmid, path)

    def read_file_from_vm_id(self, node: str, vmid: int, path: PurePosixPath | str) -> dict:
        if type(path) == str:
            path = PurePosixPath(path)
        return self.nodes(node).qemu(vmid).agent("file-read").get(file= path) or {}
    
    def get_vmids(self) -> list:
        vms = self.cluster.resources.get(type="vm") or []
        return [vm["vmid"] for vm in vms if "vmid" in vm]
    
    def get_next_vmid(self) -> int:
        return max(99, *self.get_vmids()) + 1
    
    def start_all(self, node: str, ensure: bool = True, poll_timeout: int | float = 2, poll_attempts: int = 10, **kwargs) -> None:
        self.nodes(node).startall.post(**kwargs)
        if ensure:
            while not all([vm.get("status") == "running" for vm in self.nodes(node).qemu.get() or [] if str(vm.get("vmid")) in kwargs["vms"]]):
                if poll_attempts == 0:
                    raise Exception(f"Node {node} timed out while waiting for all vms to start.")
                poll_attempts -= 1
                sleep(poll_timeout)

    def stop_all(self, node: str, ensure: bool = True, poll_timeout: int | float = 1, poll_attempts: int = 10, **kwargs) -> None:
        self.nodes(node).stopall.post(**kwargs)
        if ensure:
            while not all([vm.get("status") == "stopped" for vm in self.nodes(node).qemu.get() or [] if str(vm.get("vmid")) in kwargs["vms"]]):
                if poll_attempts == 0:
                    raise Exception(f"Node {node} timed out while waiting for all vms to stop.")
                poll_attempts -= 1
                sleep(poll_timeout)
    
    
# if __name__ == "__main__":
#     from creds import PROXMOX_HOST, TOKEN_USER, TOKEN_ID, TOKEN_VALUE

#     env = proxmox_helper(host= PROXMOX_HOST, user=TOKEN_USER, token_name= TOKEN_ID, token_value=TOKEN_VALUE, verify_ssl=False)
#     print(env.get_ip_qemu_vm_id("cyberb", 107, "BC:24:11:0F:8B:33"))
#     # env.write_file_to_vm_id("cyberb", 105, "/root/test.txt", b"test\n\xff\x01")
#     # print(env.read_file_from_vm_id("cyberb", 105, "/root/configure_router.sh"))
#     with open("configure_router.sh", "rb") as file:
#         env.write_file_to_vm_id("cyberb", 105, "/root/cyberb/configure_router.sh", file.read1())
#     print(env.run_commands_vm("cyberb", "testvm", ["bash /root/configure_router.sh BC:24:11:1C:93:96 BC:24:11:FB:A1:09 192.168.3.0/24"], poll_attempts= 200))
    # env.create_qemu_vm("cyberb", name= "testvm")
    # vmid = env.get_qemu_vms("cyberb")["testvm"]
    # env.edit_qemu_vm("cyberb", "testvm", cdrom= "local:iso/live-image-amd64.hybrid.iso", agent= "enabled=1")
    # env.start_qemu_vm("cyberb", "testvm")
    # try:
    #     env.wait_for_qemu_agent("cyberb", "testvm")
    #     print(env.run_commands_vm("cyberb", "testvm", ["mkdir -p /hello", "ls -la /hello", " whoami && sleep 10"], poll_attempts= 20).get("out-data"))
    # except Exception as e:
    #     print(e)
    # env.delete_qemu_vms("cyberb", ["testvm"])
    # print(env.ensure_state_qemu_vm("cyberb", "testvm", ["absent"], poll_attempts=5))