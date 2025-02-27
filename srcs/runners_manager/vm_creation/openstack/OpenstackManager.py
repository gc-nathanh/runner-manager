import asyncio
import logging
import time

import glanceclient.client as glance_client
import keystoneauth1.session
import keystoneclient.auth.identity.v3
import neutronclient.v2_0.client
import novaclient.client
import novaclient.v2.servers
from runners_manager.monitoring.prometheus import metrics
from runners_manager.runner.Runner import Runner
from runners_manager.runner.Runner import VmType
from runners_manager.vm_creation.CloudManager import CloudManager
from runners_manager.vm_creation.CloudManager import create_vm_metric
from runners_manager.vm_creation.CloudManager import delete_vm_metric
from runners_manager.vm_creation.openstack.schema import OpenstackConfig
from runners_manager.vm_creation.openstack.schema import OpenstackConfigVmType


logger = logging.getLogger("runner_manager")


class OpenstackManager(CloudManager):
    """
    Manager related to Openstack virtual machines
    """

    CONFIG_SCHEMA = OpenstackConfig
    CONFIG_VM_TYPE_SCHEMA = OpenstackConfigVmType
    nova_client: novaclient.client.Client
    neutron: neutronclient.v2_0.client.Client
    network_name: str
    settings: dict

    def __init__(
        self,
        name: str,
        settings: dict,
        redhat_username: str,
        redhat_password: str,
        ssh_keys: str,
    ):
        super(OpenstackManager, self).__init__(
            name, settings, redhat_username, redhat_password, ssh_keys
        )

        if settings.get("username") and settings.get("password"):
            logger.info("Openstack auth with basic credentials")
            session = keystoneauth1.session.Session(
                auth=keystoneclient.auth.identity.v3.Password(
                    auth_url=settings["auth_url"],
                    username=settings["username"],
                    password=settings["password"],
                    user_domain_name="default",
                    project_name=settings["project_name"],
                    project_domain_id="default",
                )
            )
        elif settings.get("username") and settings.get("token"):
            logger.info("Openstack auth with token")
            session = keystoneauth1.session.Session(
                auth=keystoneclient.auth.identity.v3.Token(
                    auth_url=settings["auth_url"],
                    token=settings["token"],
                    project_name=settings["project_name"],
                    project_domain_id="default",
                )
            )
        elif settings.get("id") and settings.get("secret"):
            logger.info("Openstack appcred with AppCred")
            application_credential = keystoneauth1.identity.v3.ApplicationCredentialMethod(
                application_credential_secret=settings["secret"],
                application_credential_id=settings["id"]
            )
            session = keystoneauth1.session.Session(
                auth=keystoneclient.auth.identity.v3.Auth(
                    auth_url=settings["auth_url"],
                    auth_methods=[application_credential]
                )
            )
        else:
            raise Exception(
                "You should have infos for openstack / cloud nine connection"
            )

        self.network_name = settings["network_name"]
        self.nova_client = novaclient.client.Client(
            version=2, session=session, region_name=settings["region_name"]
        )
        self.neutron = neutronclient.v2_0.client.Client(
            session=session, region_name=settings["region_name"]
        )
        self.glance = glance_client.Client(
            "2", session=session, region_name=settings["region_name"]
        )

    def get_all_vms(self, prefix: str) -> list[Runner]:
        """
        Return the list of virtual machines releated to Github runner
        """
        return [
            Runner(
                vm.name,
                vm.id,
                VmType(
                    {
                        "tags": [],
                        "config": {
                            "image": self.glance.images.get(vm.image["id"]).name,
                            "flavor": self.nova_client.flavors.get(
                                vm.flavor["id"]
                            ).name,
                        },
                        "quantity": {},
                    }
                ),
                self.name,
            )
            for vm in self.nova_client.servers.list(sort_keys=["created_at"])
            if vm.name.startswith(prefix)
        ]

    @create_vm_metric
    def create_vm(
        self,
        runner: Runner,
        runner_token: int or None,
        github_organization: str,
        installer: str,
        call_number=0,
    ) -> int or None:
        """
        Every call with nova_client looks very unstable.

        Create a vm with the default security group and config network for nic,
            and asked image / flavor
        Wait until the vm is cleanly created by openstack, in the other case delete and recreate it.
        After 4 retry the function stop.
        """
        self.CONFIG_VM_TYPE_SCHEMA().load(runner.vm_type.config)

        if call_number > 10:
            return None

        instance = None
        try:
            # Delete all VMs with the same name
            vm_list = self.nova_client.servers.list(
                search_opts={"name": runner.name}, sort_keys=["created_at"]
            )
            for vm in vm_list:
                self.nova_client.servers.delete(vm.id)
    
            sec_group_id = self.neutron.list_security_groups(name="default")["security_groups"][0][
                "id"
            ]
            net = self.neutron.list_networks(name=self.network_name)["networks"][0][
                "id"
            ]
            nic = {"net-id": net}
            nic_config = {'port': {
                   'network_id': net,
                   'name': runner.name,
                   'admin_state_up': True,
                   'security_groups': [sec_group_id]
            }}
            nic = self.neutron.create_port(body=nic_config)
            image = self.nova_client.glance.find_image(runner.vm_type.config["image"])
            flavor = self.nova_client.flavors.find(name=runner.vm_type.config["flavor"])
            nic_id = nic['port']['id']
            nic_def = {"port-id": nic_id}
            instancenics = [nic_def]
            
            #RNIC stuff        
            if "rnic_network_name" in runner.vm_type.config:
                logger.info("RNIC connectivity required")
                rnic_net = self.neutron.list_networks(name=runner.vm_type.config["rnic_network_name"])["networks"][0][
                    "id"
                ]
                rnic_config = {'port': {
                    'network_id': rnic_net,
                    'name': runner.name,
                    'admin_state_up': True,
                    'binding:vnic_type': 'direct',
                    'port_security_enabled': False
                }}
                rnic = self.neutron.create_port(body=rnic_config)
                rnic_id = rnic['port']['id']
                rnic_def = {"port-id": rnic_id}
                instancenics.append(rnic_def)

            # IPUOF stuff
            meta_config = {}
            if "partition_name" in runner.vm_type.config:
                logger.info("IPUOF config required")
                meta_config = { "partition_name": runner.vm_type.config["partition_name"], "vipu_ipaddr": runner.vm_type.config["vipu_ipaddr"], "vipu_port": runner.vm_type.config["vipu_port"]  }

            if "ntphost_ipaddr" in runner.vm_type.config:
                logger.info("Adding NTP server config")
                meta_config[ "ntphost_ipaddr" ] = runner.vm_type.config["ntphost_ipaddr"]

            if "loghost_ipaddr" in runner.vm_type.config:
                logger.info("Adding Log server config")
                meta_config[ "loghost_ipaddr" ] = runner.vm_type.config["loghost_ipaddr"]

            instance = self.nova_client.servers.create(
                name=runner.name,
                meta=meta_config,
                image="",
                flavor=flavor,
                security_groups=None,
                nics=instancenics,
                block_device_mapping_v2=[ { "source_type": "image", "destination_type": "volume", "uuid": image.id, "delete_on_termination": "true", "boot_index": "0", "volume_size": runner.vm_type.config["root_volume_size"] } ],
                availability_zone=runner.vm_type.config["availability_zone"],
                userdata=self.script_init_runner(
                    runner, runner_token, github_organization, installer
                ),
            )

            while instance.status not in ["ACTIVE", "ERROR"]:
                instance = self.nova_client.servers.get(instance.id)
                time.sleep(2)

            if instance.status == "ERROR":
                logger.info("vm failed, creating a new one")
                self.delete_vm(runner)
                time.sleep(2)
                metrics.runner_creation_failed.labels(cloud=self.name).inc()
                return self.create_vm(
                    runner,
                    runner_token,
                    github_organization,
                    installer,
                    call_number + 1,
                )
        except Exception as e:
            logger.error(f"Vm creation raised an error, {e}")

        if not instance or not instance.id:
            metrics.runner_creation_failed.labels(cloud=self.name).inc()
            logger.error(
                f"""VM not found on openstack, recreating it.
VM id: {instance.id if instance else 'Vm not created'}"""
            )
            # Delete any leftover ports with the same name
            port_list = self.neutron.list_ports(name=runner.name)
            for port in port_list['ports']:
                logger.info("deleting port:")
                logger.info(port['id'])
                self.neutron.delete_port(port=port['id'])
            return self.create_vm(
                runner, runner_token, github_organization, installer, call_number + 1
            )

        logger.info("vm is successfully created")
        return instance.id

    @delete_vm_metric
    def delete_vm(self, runner: Runner):
        """
        Delete a vm synchronously  if there is a running loop or normally if it can't
        """
        self.CONFIG_VM_TYPE_SCHEMA().load(runner.vm_type.config)
        try:
            asyncio.get_running_loop().run_in_executor(
                None, self.async_delete_vm, runner
            )
        except RuntimeError:
            self.async_delete_vm(runner)

    def async_delete_vm(self, runner: Runner):
        """
        If the image name is a rhel shelve, so we have a clean poweroff and
            the VM can un subscribe its certificate by its own.

        Then delete the virtual machin
        """
        self.CONFIG_VM_TYPE_SCHEMA().load(runner.vm_type.config)
        try:
            if (
                runner.vm_type.config["image"]
                and "rhel" in runner.vm_type.config["image"]
            ):
                try:
                    nb_error = 0
                    self.nova_client.servers.shelve(runner.vm_id)
                    s = self.nova_client.servers.get(runner.vm_id).status
                    while s not in ["SHUTOFF", "SHELVED_OFFLOADED"] and nb_error < 5:
                        time.sleep(5)
                        try:
                            s = self.nova_client.servers.get(runner.vm_id).status
                            logger.info(s)
                        except Exception as e:
                            nb_error += 1
                            logger.error(f"Error in VM delete {e}")

                except Exception:
                    pass
            nics=self.nova_client.servers.interface_list(runner.vm_id)
            self.nova_client.servers.delete(runner.vm_id)
            for deletenics in nics:
                logger.info("deleting port:")
                logger.info(deletenics)
                self.neutron.delete_port(port=deletenics.id)

        except novaclient.exceptions.NotFound as exp:
            # If the machine was already deleted, move along
            logger.info(exp)
            pass

    def delete_images_from_shelved(self, name: str):
        images = self.glance.images.list()

        for i in images:
            if name in i.name:
                self.glance.images.delete(i.id)
