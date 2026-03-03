# tests/test_proxmox_helper_unittest.py
# type: ignore
import unittest
from unittest.mock import Mock, call
from proxmox_helper import proxmox_helper
from pathlib import PurePosixPath

class TestProxmoxHelper(unittest.TestCase):
    """All tests for proxmox_helper – same assertions as the pytest version."""

    def setUp(self):
        """Create a helper instance and mock its network attributes."""
        self.helper = proxmox_helper(backend="local")
        self.helper.nodes = Mock()
        self.helper.cluster = Mock()

    # ---------- get_nodes ----------
    def test_get_nodes(self):
        self.helper.nodes.get.return_value = [{"node": "node1"}, {"node": "node2"}]
        nodes = self.helper.get_nodes()
        self.assertEqual(nodes, ["node1", "node2"])
        self.helper.nodes.get.assert_called_once()

    # ---------- get_networks ----------
    def test_get_networks(self):
        self.helper.nodes.return_value.network.get.return_value = [{"iface": "vmbr0", "test_key":"test_value"}, {"iface": "lo", "test_key":"test_value"}]
        nics = self.helper.get_networks("node1", types=["any_bridge"])
        self.assertEqual(nics, ["vmbr0", "lo"])
        self.helper.nodes.return_value.network.get.assert_called_once_with(type="any_bridge")
        nics = self.helper.get_networks("node1", types=["any_bridge"], full= True)
        self.assertEqual(nics, [{"iface": "vmbr0", "test_key":"test_value"}, {"iface": "lo", "test_key":"test_value"}])

    def test_get_network(self):
        self.helper.nodes.return_value.network.return_value.get.return_value = {"iface": "vmbr0"}
        nics = self.helper.get_network("node1", "vmbr0")
        self.assertEqual(nics, {"iface": "vmbr0"})

    # ---------- delete_networks ----------
    def test_delete_networks(self):
        self.helper.delete_networks("node1", ["vmbr0", "vmbr1"])
        self.helper.nodes.return_value.network.assert_has_calls(
            [call(value) for value in ("vmbr0", "vmbr1")],
            any_order=True,
        )
        self.assertEqual(
            self.helper.nodes.return_value.network.return_value.delete.call_count,
            2,
        )

    # ---------- create_network ----------
    def test_create_network(self):
        self.helper.create_network("node1", iface="vmbr2", type="bridge")
        self.helper.nodes.return_value.network.post.assert_called_once_with(
            iface="vmbr2", type="bridge"
        )

    def test_edit_network(self):
        self.helper.edit_network("test_node", "test_iface", test_setting= "test_value")
        self.helper.nodes.return_value.network.return_value.put.assert_called_once_with(test_setting="test_value")

    def test_update_networks(self):
        self.helper.update_networks("test_node")
        self.helper.nodes.return_value.network.put.assert_called_once()

    def test_get_state_network(self):
        self.helper.get_networks = Mock(return_value=[{"iface":"test_network1", "active":1}, {"iface":"test_network2", "active":0}])
        state = self.helper.get_state_network("test_node", "test_network1")
        self.assertEqual(state, "running")
        state = self.helper.get_state_network("test_node", "test_network2")
        self.assertEqual(state, "stopped")
        state = self.helper.get_state_network("test_node", "test_network3")
        self.assertEqual(state, "absent")

    def test_ensure_state_network(self):
        self.helper.get_state_network = Mock(return_value= "running")
        is_state = self.helper.ensure_state_network("test_node", "test_network1", ["running"], 0)
        self.assertTrue(is_state)
        is_state = self.helper.ensure_state_network("test_node", "test_network1", ["absent"], 0)
        self.assertFalse(is_state)

    def test_vm_name_to_id(self):
        self.helper.get_qemu_vms = Mock(return_value={"VM1": 100, "VM2": 200})
        vmid = self.helper.vm_name_to_id("test_node", "VM1")
        self.assertEqual(vmid, 100)
        with self.assertRaises(Exception) as cm:
            self.helper.vm_name_to_id("test_node", "VM3")
        self.assertIn("VM named VM3 does not exist.", str(cm.exception))

    def test_get_qemu_vms(self):
        self.helper.nodes.return_value.qemu.get.return_value=[{"name":"test_name1", "vmid": 100}, {"vmid":101}, {"name":"fail"}, {}]
        vms = self.helper.get_qemu_vms("test_node")
        self.assertEqual(vms, {"test_name1":100})
        self.helper.nodes.return_value.qemu.get.return_value=None
        vms = self.helper.get_qemu_vms("test_node")
        self.assertEqual(vms, {})

    def test_get_config_qemu_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.nodes.return_value.qemu.return_value.config.get.return_value = {"test_key":"test_value"}
        config = self.helper.get_config_qemu_vm("test_node", "VM1")
        self.assertEqual(config, {"test_key":"test_value"})

    def test_delete_qemu_vms(self):
        self.helper.get_qemu_vms = Mock(return_value={"VM1": 100, "VM2": 200})
        self.helper.ensure_state_qemu_vm_id = Mock(return_value= True)
        self.helper.stop_qemu_vm_id = Mock()
        self.helper.delete_qemu_vms("test_node", ["VM1", "VM2"])
        self.helper.nodes.return_value.qemu.return_value.delete.assert_called_with("?destroy-unreferenced-disks=1&purge=1")
        self.helper.stop_qemu_vm_id.assert_called()

    def test_create_qemu_vm(self):
        self.helper.get_qemu_vms = Mock(return_value={"VM1": 100, "VM2": 200})
        self.helper.get_next_vmid = Mock(return_value=201)
        self.helper.create_qemu_vm("test_node")
        self.helper.nodes.return_value.qemu.post.assert_called_once_with(vmid=201)
        with self.assertRaises(Exception) as cm:
            self.helper.create_qemu_vm("test_node", name="VM1")
        self.assertIn("Name VM1 is not unique", str(cm.exception))

    def test_edit_qemu_vm(self):
        self.helper.get_qemu_vms = Mock(return_value={"VM1": 100, "VM2": 200})
        self.helper.edit_qemu_vm("test_node", "VM1", test_setting="test_value")
        self.helper.nodes.return_value.qemu.return_value.config.post.assert_called_once_with(test_setting="test_value")

    def test_start_qemu_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.start_qemu_vm("test_node", "VM1", test_setting="test_value")
        self.helper.nodes.return_value.qemu.return_value.status.start.post.assert_called_once_with(test_setting="test_value")

    def test_stop_qemu_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.stop_qemu_vm("test_node", "VM1", test_setting="test_value")
        self.helper.nodes.return_value.qemu.return_value.status.stop.post.assert_called_once_with(test_setting="test_value", **{"overrule-shutdown":1})

    def test_reset_qemu_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.reset_qemu_vm("test_node", "VM1")
        self.helper.nodes.return_value.qemu.return_value.status.reset.post.assert_called_once()

    def test_get_state_qemu_vms(self):
        self.helper.nodes.return_value.qemu.get.return_value = [{"name":"test_name1", "vmid": 100, "status": "running"}, {"name":"test_name2", "vmid": 200, "status": "stopped"}]
        vms = self.helper.get_state_qemu_vms("test_node")
        self.assertEqual(vms, [{"name":"test_name1", "vmid": 100, "status": "running"}, {"name":"test_name2", "vmid": 200, "status": "stopped"}])
        self.helper.nodes.return_value.qemu.get.return_value = None
        vms = self.helper.get_state_qemu_vms("test_node")
        self.assertEqual(vms, [])

    def test_get_state_qemu_vm(self):
        self.helper.nodes.return_value.qemu.get.return_value = [{"name":"test_name1", "vmid": 100, "status": "running"}, {"name":"test_name2", "vmid": 200, "status": "stopped"}]
        vm = self.helper.get_state_qemu_vm("test_node", "test_name1")
        self.assertEqual(vm, "running")
        vm = self.helper.get_state_qemu_vm("test_node", "test_name2")
        self.assertEqual(vm, "stopped")
        vm = self.helper.get_state_qemu_vm("test_node", "test_name3")
        self.assertEqual(vm, "absent")

    def test_ensure_state_qemu_vm(self):
        self.helper.nodes.return_value.qemu.get.return_value = [{"name":"test_name1", "vmid": 100, "status": "running"}, {"name":"test_name2", "vmid": 200, "status": "stopped"}]
        self.assertTrue(self.helper.ensure_state_qemu_vm("test_node", "test_name3", ["absent"]))
        self.assertTrue(self.helper.ensure_state_qemu_vm("test_node", "test_name1", ["running"]))
        self.assertTrue(self.helper.ensure_state_qemu_vm("test_node", "test_name2", ["stopped"]))
        self.assertFalse(self.helper.ensure_state_qemu_vm("test_node", "test_name1", ["stopped"], poll_timeout=0))
        with self.assertRaises(Exception) as cm:
            self.helper.ensure_state_qemu_vm("test_node", "VM3", ["stopped"])
        self.assertIn("VM named VM3 does not exist.", str(cm.exception))

    def test_wait_for_qemu_agent(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.wait_for_qemu_agent("test_node", "VM1")
        self.helper.nodes.return_value.qemu.return_value.agent.ping.post.assert_called_once()
        self.helper.nodes.return_value.qemu.return_value.agent.ping.post.side_effect = Exception("500 Internal Server Error: QEMU guest agent is not running")
        with self.assertRaises(Exception) as cm:
            self.helper.wait_for_qemu_agent("test_node", "VM1", poll_timeout=0)
        self.assertIn("VM with id:100 timed out while waiting for qemu agent.", str(cm.exception))
        self.helper.nodes.return_value.qemu.return_value.agent.ping.post.side_effect = Exception("test")
        with self.assertRaises(Exception) as cm:
            self.helper.wait_for_qemu_agent("test_node", "VM1", poll_timeout=0)
        self.assertIn("test", str(cm.exception))

    # ---------- run_commands_vm ----------
    def test_run_commands_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.nodes.return_value.qemu.return_value.agent.exec.post = Mock(
            return_value={"pid": 1}
        )
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.get = Mock(
            return_value={"exited": 1}
        )

        resp = self.helper.run_commands_vm("node1", "test-vm", ["echo hello"])
        self.assertEqual(resp, {"exited": 1})

        self.helper.nodes.return_value.qemu.assert_called_with(100)
        self.helper.nodes.return_value.qemu.return_value.agent.exec.post.assert_called_once_with(
            command=["bash", "-c", ";".join(["echo hello"])]
        )
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.get.assert_called_with(pid=1)

    # ---------- run_commands_vm_id – error handling ----------
    def test_run_commands_vm_id_error1(self):
        self.helper.nodes.return_value.qemu.return_value.agent.exec.post = Mock(
            return_value=None
        )
        with self.assertRaises(Exception) as cm:
            self.helper.run_commands_vm_id("node1", 200, ["whoami"])
        self.assertIn("Agent did not return a response", str(cm.exception))

    def test_run_commands_vm_id_error2(self):
        self.helper.nodes.return_value.qemu.return_value.agent.exec.post = Mock(
            return_value={"pid": 1}
        )
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.get = Mock(
            return_value=None
        )
        with self.assertRaises(Exception) as cm:
            self.helper.run_commands_vm_id("node1", 200, ["whoami"], poll_timeout=0)
        self.assertIn("Command execution timed out", str(cm.exception))
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.get.assert_has_calls([call(pid=1)]*10)

    def test_write_file_to_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.write_file_to_vm("test_node", "test-vm", "/test", bytes(range(256)))
        file_B64 = 'AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8gISIjJCUmJygpKissLS4vMDEyMzQ1Njc4OTo7PD0+P0BBQkNERUZHSElKS0xNTk9QUVJTVFVWV1hZWltcXV5fYGFiY2RlZmdoaWprbG1ub3BxcnN0dXZ3eHl6e3x9fn+AgYKDhIWGh4iJiouMjY6PkJGSk5SVlpeYmZqbnJ2en6ChoqOkpaanqKmqq6ytrq+wsbKztLW2t7i5uru8vb6/wMHCw8TFxsfIycrLzM3Oz9DR0tPU1dbX2Nna29zd3t/g4eLj5OXm5+jp6uvs7e7v8PHy8/T19vf4+fr7/P3+/w=='
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.post.assert_called_once_with(file='/test', content=file_B64, encode=0)
        self.helper.nodes.reset_mock()
        self.helper.write_file_to_vm("test_node", "test-vm", "/test", "dGVzdA==")
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.post.assert_called_once_with(file='/test', content='dGVzdA==', encode=0)

    def test_read_file_from_vm(self):
        self.helper.vm_name_to_id = Mock(return_value=100)
        self.helper.read_file_from_vm("test_node", "test-vm", "/test")
        self.helper.nodes.return_value.qemu.return_value.agent.return_value.get.assert_called_once_with(file=PurePosixPath('/test'))

    # ---------- get_vmids & get_next_vmid ----------
    def test_vmids_and_next(self):
        self.helper.cluster.resources.get.return_value = [
            {"vmid": 101}, {"vmid": 102}, {"vmid": 150}
        ]
        vmids = self.helper.get_vmids()
        self.assertEqual(vmids, [101, 102, 150])

        next_id = self.helper.get_next_vmid()
        self.assertEqual(next_id, 151)

    def test_start_all(self):
        self.helper.nodes.return_value.qemu.get.return_value = [{"vmid":100, "status": "running"}, {"vmid":101, "status": "stopped"}]
        self.helper.start_all("test_node", force=1, vms= ",100")
        self.helper.nodes.return_value.startall.post.assert_called_once_with(force=1, vms= ",100")
        with self.assertRaises(Exception) as cm:
            self.helper.start_all("test_node", timeout=1, vms= ",101", poll_timeout=0)
        self.assertIn("Node test_node timed out while waiting for all vms to start.", str(cm.exception))

    def test_stop_all(self):
        self.helper.nodes.return_value.qemu.get.return_value = [{"vmid":100, "status": "stopped"}, {"vmid":101, "status": "running"}]
        self.helper.stop_all("test_node", timeout=1, vms= ",100")
        self.helper.nodes.return_value.stopall.post.assert_called_once_with(timeout=1, vms= ",100")
        with self.assertRaises(Exception) as cm:
            self.helper.stop_all("test_node", timeout=1, vms= ",101", poll_timeout=0)
        self.assertIn("Node test_node timed out while waiting for all vms to stop.", str(cm.exception))