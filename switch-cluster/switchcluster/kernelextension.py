ipykernel_imported = True
try:
    from ipykernel import zmqshell
except ImportError:
    ipykernel_imported = False

import os, logging, tempfile, subprocess
import io, yaml
import subprocess
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import base64
from os.path import join, dirname
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To, From


class SwitchCluster:
    def __init__(self, ipython, log):
        self.ipython = ipython
        self.log = log

    def send(self, msg):
        """Send a message to the frontend"""
        self.comm.send(msg)

    def send_ok(self, page, config=None):
        """Send a message to frontend to switch to a specific page and append spark config"""
        self.send({'msgtype': page, 'config': config})

    def send_error(self, page, error):
        """Send a message to frontend to switch to a specific page and append error message"""
        self.send({'msgtype': page, 'error': error})

    def handle_comm_message(self, msg):
        """ Handle message received from frontend """
        # self.log.info(msg)
        action = msg['content']['data']['action']

        if action == 'Refresh':
            pass
            self.cluster_list()
        elif action == 'change-current-context':
            context = msg['content']['data']['context']
            # self.log.info("Changed context for kubeconfig!")


            self.log.info("Context from frontend: ", context)

            with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                load = yaml.safe_load(stream)

            load['current-context'] = context

            with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)

            self.send({
                'msgtype': 'changed-current-context'
            })
        elif action == 'check-current-settings':
            cluster = msg['content']['data']['cluster']
            namespace = msg['content']['data']['namespace']
            svcaccount = msg['content']['data']['svcaccount']

            self.check_config(cluster, namespace, svcaccount)
        elif action == 'get-context-settings':
            context = msg['content']['data']['context']

            self.log.info("View Context: ", context)

            with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                load = yaml.safe_load(stream)

            for i in load['contexts']:
                if i['name'] == context:
                    cluster_name = i['context']['cluster']
                    user_name = i['context']['user']
                    namespace_name = i['context']['namespace']

            self.log.info("Cluster name: ", cluster_name)
            self.log.info("Service account name: ", user_name)
            self.log.info("Namespace name: ", namespace_name)

            os.environ['KUBECONFIG'] = os.environ['HOME'] + '/.kube/config'
            os.environ['NAMESPACE'] = namespace_name
            os.environ['SERVICE_ACCOUNT'] = user_name

            token = subprocess.check_output('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test3.sh', shell=True)
            token = base64.b64decode(token)
            self.log.info("Token: ", str(token))

            self.send({
                'msgtype': 'context-info',
                'cluster_name': cluster_name,
                'svcaccount': user_name,
                'namespace': namespace_name,
                'token': token
            })
        elif action == 'add-context':
            namespace = msg['content']['data']['namespace']
            token = msg['content']['data']['token']
            svcaccount = msg['content']['data']['svcaccount']
            context_name = msg['content']['data']['context_name']
            cluster = msg['content']['data']['cluster']
            tab = msg['content']['data']['tab']

            if tab == 'local':
                os.environ['SERVICE_ACCOUNT'] = svcaccount
                os.environ['TOKEN'] = token
                os.environ['CONTEXT_NAME'] = context_name
                os.environ['CLUSTER_NAME'] = cluster
                os.environ['NAMESPACE'] = namespace

                error = ''

                config.load_kube_config()

                contexts, active_context = config.list_kube_config_contexts()
                contexts = [i['name'] for i in contexts]

                api_instance = client.CoreV1Api()
                
                if context_name in contexts:
                    error = error + ' Context \'{}\' already exist.'.format(context_name)

                if error == '':
                    try:
                        api_response = api_instance.list_namespace()
                        namespace_names = [i.metadata.name for i in api_response.items]

                        if namespace not in namespace_names:
                            error = error + ' Namespace \'{}\' does not exist.'.format(namespace)

                    except ApiException as e:
                        error = e
                        self.log.info("Exception when calling CoreV1Api->list_namespaced_service_account: %s\n" % e)
                
                
                if error == '':
                    try:
                        api_response = api_instance.list_namespaced_service_account(namespace=namespace)
                        svcaccount_names = [i.metadata.name for i in api_response.items]
                        
                        if svcaccount not in svcaccount_names:
                            error = error + ' Service account \'{}\' does not exist.'.format(svcaccount)
                    except ApiException as e:
                        error = e
                        self.log.info("Exception when calling CoreV1Api->list_namespace: %s\n" % e)
                
                if error == '':
                    output = subprocess.call('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test4.sh', shell=True)
                    self.log.info("output: ", output)
                    if output != 0:
                        error = 'You cannot use these settings. Please contact your admin'

                if error == '':
                    self.send({
                    'msgtype': 'added-context-successfully',
                    })
                else:
                    self.send({
                    'msgtype': 'added-context-unsuccessfully',
                    'error': error
                    })
        elif action == 'add-context-cluster':
            
            tab = msg['content']['data']['tab']

            if tab == 'local':
                token = msg['content']['data']['token']
                cluster_name = msg['content']['data']['cluster_name']
                insecure_server = msg['content']['data']['insecure_server']
                ip = msg['content']['data']['ip']
                namespace = "swan-" + os.getenv('USER')
                svcaccount = os.getenv('USER')
                # context_name = cluster_name + "-" + namespace + "-" + svcaccount + "-context"
                context_name = cluster_name

                if insecure_server == "false":
                    catoken = msg['content']['data']['catoken']

                os.environ['SERVICE_ACCOUNT'] = svcaccount
                os.environ['TOKEN'] = token
                os.environ['CONTEXT_NAME'] = context_name
                os.environ['CLUSTER_NAME'] = cluster_name
                os.environ['NAMESPACE'] = namespace
                os.environ['SERVER_IP'] = ip

                if insecure_server == "false":
                    os.environ['CATOKEN'] = catoken

                error = ''
                if os.path.isdir(os.getenv('HOME') + '/.kube'):
                    if not os.path.isfile(os.getenv('HOME') + '/.kube/config'):
                        load = {}
                        load['apiVersion'] = 'v1'
                        load['clusters'] = []
                        load['contexts'] = []
                        load['current-context'] = ''
                        load['kind'] = 'Config'
                        load['preferences'] = {}
                        load['users'] = []

                        with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                            yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)                        
                else:
                    os.makedirs(os.getenv('HOME') + '/.kube')

                    load = {}
                    load['apiVersion'] = 'v1'
                    load['clusters'] = []
                    load['contexts'] = []
                    load['current-context'] = ''
                    load['kind'] = 'Config'
                    load['preferences'] = {}
                    load['users'] = []

                    with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                        yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)
                

                try:
                    with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                        load = yaml.safe_load(stream)
                except:
                    error = 'Cannot load kubeconfig'

                contexts = []
                clusters = []

                if error == '':
                    active_context = load['current-context']

                    for i in load['contexts']:
                        contexts.append(i['name'])

                    for i in load['clusters']:
                        clusters.append(i['name'])

                    if cluster_name in clusters:
                        error = error + ' Cluster \'{}\' already exist.'.format(cluster_name)
                    
                    if error == '':
                        if insecure_server == "false":
                            load['clusters'].append({
                                'cluster': {
                                    'certificate-authority-data': catoken,
                                    'server': ip
                                },
                                'name': cluster_name
                            })
                        else:
                            load['clusters'].append({
                                'cluster': {
                                    'insecure-skip-tls-verify': True,
                                    'server': ip
                                },
                                'name': cluster_name
                            })

                        try:
                            with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                                yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)
                        except:
                            error = 'Cannot write to KUBECONFIG'

                if error == '':
                    output = subprocess.call('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test5.sh', shell=True)
                    self.log.info("output: ", output)
                    if output != 0:
                        error = 'There is some error. You cannot use these settings. Please contact your admin'

                if error == '':
                    try:        
                        api_instance2 = client.CoreV1Api(api_client=config.new_client_from_config(context=context_name))
                        api_response = api_instance2.list_namespaced_pod(namespace=namespace)
                        self.log.info(api_response)
                    except ApiException as e:
                        error = 'You cannot request resources using these settings. Please contact your admin'
                        output = subprocess.call('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test6.sh', shell=True)
                        self.log.info("output: ", output)
                        if output != 0:
                            error = 'There is some error. You cannot use these settings. Please contact your admin'

                if error == '':
                    self.send({
                    'msgtype': 'added-context-successfully',
                    })
                else:
                    self.send({
                    'msgtype': 'added-context-unsuccessfully',
                    'error': error
                    })

            elif tab == 'openstack':
                ostoken = msg['content']['data']['ostoken']
                cluster_name = msg['content']['data']['cluster_name']
                ip = msg['content']['data']['ip']
                catoken = msg['content']['data']['catoken']
                namespace = "swan-" + os.getenv('USER')
                svcaccount = os.getenv('USER')
                # context_name = cluster_name + "-" + namespace + "-" + svcaccount + "-context"
                context_name = cluster_name

                error = ''
                if os.path.isdir(os.getenv('HOME') + '/.kube'):
                    if not os.path.isfile(os.getenv('HOME') + '/.kube/config'):
                        load = {}
                        load['apiVersion'] = 'v1'
                        load['clusters'] = []
                        load['contexts'] = []
                        load['current-context'] = ''
                        load['kind'] = 'Config'
                        load['preferences'] = {}
                        load['users'] = []

                        with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                            yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)                        
                else:
                    os.makedirs(os.getenv('HOME') + '/.kube')

                    load = {}
                    load['apiVersion'] = 'v1'
                    load['clusters'] = []
                    load['contexts'] = []
                    load['current-context'] = ''
                    load['kind'] = 'Config'
                    load['preferences'] = {}
                    load['users'] = []

                    with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                        yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)

                try:
                    with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                        load = yaml.safe_load(stream)
                except:
                    error = 'Cannot load KUBECONFIG'
                
                clusters = []
                if error == '':
                    for i in load['clusters']:
                        clusters.append(i['name'])

                    if cluster_name in clusters:
                        error = error + ' Cluster \'{}\' already exist.'.format(cluster_name)

                    if error == '':
                        user_exec_command = {'exec': {'args': ['-c', 'if [ -z ${OS_TOKEN} ]; then\n    echo \'Error: Missing OpenStack credential from environment variable $OS_TOKEN\' > /dev/stderr\n    exit 1\nelse\n    echo \'{ "apiVersion": "client.authentication.k8s.io/v1alpha1", "kind": "ExecCredential", "status": { "token": "\'"${OS_TOKEN}"\'"}}\'\nfi\n'], 'command': '/bin/bash', 'apiVersion': 'client.authentication.k8s.io/v1alpha1'}}

                        load['clusters'].append({
                            'cluster': {
                                'certificate-authority-data': catoken,
                                'server': ip
                            },
                            'name': cluster_name
                        })

                        load['contexts'].append({
                            'context': {
                                'cluster': cluster_name,
                                'namespace': namespace,
                                'user': svcaccount
                            },
                            'name': context_name
                        })

                        load['users'].append({
                            'user': user_exec_command,
                            'name': svcaccount
                        })

                        try:
                            with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                                yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)
                        except:
                            error = 'Cannot write to KUBECONFIG'

                    if error == '':
                        try:
                            api_instance2 = client.CoreV1Api(api_client=config.new_client_from_config(context=context_name))
                            api_response = api_instance2.list_namespaced_pod(namespace=namespace)
                            self.log.info(api_response)
                        except ApiException as e:
                            error = 'You cannot request resources using these settings. Please contact your admin'
                            output = subprocess.call('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test6.sh', shell=True)
                            self.log.info("output: ", output)
                            if output != 0:
                                error = 'There is some error. You cannot use these settings. Please contact your admin'

                if error == '':
                    self.send({
                    'msgtype': 'added-context-successfully',
                })
                else:
                    self.send({
                    'msgtype': 'added-context-unsuccessfully',
                    'error': error
                })
        elif action == "show-error":
            error = "Please fill all the required fields."
            self.send({
                'msgtype': 'added-context-unsuccessfully',
                'error': error
            })
        elif action == "get-connection-detail":
            self.log.info("INSIDE CONNECTION DETAIL")
            error = ''
            namespace = 'default'

            try:
                with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                    load = yaml.safe_load(stream)
            except:
                error = 'Cannot load KUBECONFIG'


            if error == '':
                contexts = load['contexts']
                for i in contexts:
                    if i['name'] == load['current-context']:
                        if 'namespace' in i['context'].keys():
                            namespace = i['context']['namespace']
                            break

            self.log.info("NAMESPACE: ", namespace)
            
            if error == '':
                try:
                    config.load_kube_config()
                    api_instance = client.CoreV1Api()
                    api_response = api_instance.list_namespaced_pod(namespace=namespace, timeout_seconds=15)
                except:
                    self.log.info("CANNOT LIST PODS")
                    error = 'Cannot list pods'
            
            if error == '':
                self.send({
                    'msgtype': 'connection-details',
                    'context': load['current-context']
                })
            else:
                self.send({
                    'msgtype': 'connection-details-error',
                })

        elif action == "delete-current-context":
            error = ''

            context = msg['content']['data']['context']


            try:
                with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                    load = yaml.safe_load(stream)
            except:
                error = "Cannot open KUBECONFIG file"

            if error == '':
                for i in range(len(load['contexts'])):
                    if load['contexts'][i]['name'] == context:
                        load['contexts'].pop(i)
                        break

                try:
                    with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                        yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)
                except:
                    error = "Cannot save KUBECONFIG file"

            
            
            if error == '':
                self.send({
                    'msgtype': 'deleted-context-successfully',
                })
            else:
                self.send({
                    'msgtype': 'deleted-context-unsuccessfully',
                })
        elif action == "create-user":
            error = ''
            username = msg['content']['data']['username']
            email = msg['content']['data']['email']
            selected_context = msg['content']['data']['context']

            namespace = 'swan-' + username
            username = username
            rolebinding_name = 'edit-cluster-' + namespace

            try:
                config.load_kube_config()
            except:
                error = 'Cannot load KUBECONFIG'

            try:
                with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                    load = yaml.safe_load(stream)
            except:
                error = 'Cannot load kubeconfig'

            self.log.info("Yaml load: ", load)
            self.log.info("SELECTED CONTEXT: ", selected_context)
            if error == '':
                for i in load['contexts']:
                    if i['name'] == selected_context:
                        selected_cluster = i['context']['cluster']
                        break

            self.log.info("SELECTED CLUSTER: ", selected_cluster)

            api_instance = client.CoreV1Api()
            rbac_client = client.RbacAuthorizationV1Api()
            flag = 0
            flag1 = 0
            if error == '':
                try:
                    api_response = api_instance.list_namespace()
                    for i in api_response.items:
                        if i.metadata.name == namespace:
                            flag = 1
                            break 
                except:
                    error = 'Cannot list namespace'

            if error == '':
                if flag == 1:
                    try:
                        api_response = rbac_client.list_namespaced_role_binding(namespace=namespace)
                        for i in api_response.items:
                            if i.metadata.name == rolebinding_name:
                                # error = 'A user \'{}\' already exists for this cluster'.format(username)
                                flag1 = 1
                                break
                    except:
                        error = 'Cannot list namespaced role binding'

                    if error == '' and flag1 == 0:
                        rolebinding_obj = client.V1ObjectMeta(name=rolebinding_name, namespace=namespace, cluster_name=selected_cluster)
                        role_ref = client.V1RoleRef(api_group='rbac.authorization.k8s.io', kind='ClusterRole', name='edit')
                        subject = client.V1Subject(api_group='rbac.authorization.k8s.io', kind='User', name=username)
                        subject_list = [subject]
                        rolebinding_body = client.V1RoleBinding(metadata=rolebinding_obj, role_ref=role_ref, subjects=subject_list)

                        try:
                            rbac_client.create_namespaced_role_binding(namespace, rolebinding_body)
                        except:
                            error = 'Cannot create role binding'
                else:
                    obj = client.V1ObjectMeta(name=namespace, cluster_name=selected_cluster)
                    body = client.V1Namespace(metadata=obj)

                    try:
                        api_instance.create_namespace(body)
                    except:
                        error = 'Cannot create namespace'

                    
                    if error == '':
                        rolebinding_obj = client.V1ObjectMeta(name=rolebinding_name, namespace=namespace, cluster_name=selected_cluster)
                        role_ref = client.V1RoleRef(api_group='rbac.authorization.k8s.io', kind='ClusterRole', name='edit')
                        subject = client.V1Subject(api_group='rbac.authorization.k8s.io', kind='User', name=username)
                        subject_list = [subject]
                        rolebinding_body = client.V1RoleBinding(metadata=rolebinding_obj, role_ref=role_ref, subjects=subject_list)

                        try:
                            rbac_client.create_namespaced_role_binding(namespace, rolebinding_body)
                        except:
                            error = 'Cannot create role binding'


            # if error == '':
            # 	for i in load['contexts']:
            # 		if i['name'] == selected_context:
            # 			selected_cluster = i['context']['cluster']
            # 			break


                for i in load['clusters']:
                    if i['name'] == selected_cluster:
                        server_ip = i['cluster']['server']
                        ca_cert = i['cluster']['certificate-authority-data']
                        break

                dotenv_path = join(dirname(__file__), '.env')
                load_dotenv(dotenv_path)

                # sendgrid_api_key = os.getenv('SENDGRID_API_KEY')
                
                # html_body = '<strong>Cluster name: </strong>' + selected_cluster + '<br><br><strong>CA Cert: </strong>' + ca_cert + '<br><br><strong>Server IP: </strong>' + server_ip
                message = Mail(
                    from_email=From('sahil.jajodia@gmail.com'),
                    to_emails=To(email),
                    subject='Credentials for cluster: ' + selected_cluster,
                    html_content='<strong>Cluster name: </strong>' + selected_cluster + '<br><br><strong>CA Cert: </strong>' + ca_cert + '<br><br><strong>Server IP: </strong>' + server_ip)

                try:
                    sg = SendGridAPIClient(os.environ.get('SENDGRID_API_KEY'))
                    response = sg.send(message)
                    print(response.status_code)
                    print(response.body)
                    print(response.headers)
                except Exception as e:
                    error = e.message
                    print(e.message)

            if error == '':
                self.send({
                    'msgtype': 'added-user-successfully',
                })
            else:
                self.send({
                    'msgtype': 'added-user-unsuccessfully',
                    'error': error
                })

            # try:
            # 	api_response = rbac_client.list_namespaced_role_binding(namespace=namespace)
            # 	print(api_response)
            # except:
            # 	error = 'Cannot list namespaced role binding'




    def register_comm(self):
        """ Register a comm_target which will be used by frontend to start communication """
        self.ipython.kernel.comm_manager.register_target(
            "SwitchCluster", self.target_func)

    def target_func(self, comm, msg):
        """ Callback function to be called when a frontend comm is opened """
        self.log.info("Established connection to frontend")
        self.log.debug("Received message: %s", str(msg))
        self.comm = comm

        @self.comm.on_msg
        def _recv(msg):
            self.handle_comm_message(msg)


        self.cluster_list()

    def cluster_list(self):
        error = ''

        if os.path.isdir(os.getenv('HOME') + '/.kube'):
            if not os.path.isfile(os.getenv('HOME') + '/.kube/config'):
                load = {}
                load['apiVersion'] = 'v1'
                load['clusters'] = []
                load['contexts'] = []
                load['current-context'] = ''
                load['kind'] = 'Config'
                load['preferences'] = {}
                load['users'] = []

                with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                    yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)                        
        else:
            os.makedirs(os.getenv('HOME') + '/.kube')

            load = {}
            load['apiVersion'] = 'v1'
            load['clusters'] = []
            load['contexts'] = []
            load['current-context'] = ''
            load['kind'] = 'Config'
            load['preferences'] = {}
            load['users'] = []

            with io.open(os.environ['HOME'] + '/.kube/config', 'w', encoding='utf8') as out:
                yaml.safe_dump(load, out, default_flow_style=False, allow_unicode=True)

        try:
            with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                load = yaml.safe_load(stream)
        except:
            error = 'Cannot load kubeconfig'


        if error == '':
            contexts = load['contexts']
            for i in range(len(contexts)):
                if contexts[i]['name'] == load['current-context']:
                    active_context = contexts[i]
                    break

            self.log.info("Contexts:")
            for i in contexts:
                self.log.info(i)


            clusters = []
            for i in load['clusters']:
                clusters.append(i['name'])

            # active_context = load['current-context']

            for i in load['contexts']:
                if i['name'] == load['current-context']:
                    current_cluster = i['context']['cluster']
            
            namespaces = []
            for i in contexts:
                # self.log.info(i)
                if 'namespace' in i['context'].keys():
                    namespace = i['context']['namespace']
                    namespaces.append(namespace)
                else:
                    namespace = 'default'
                    namespaces.append(namespace)
                # self.log.info("ACTIVE CONTEXT: ", active_context)
            self.log.info("NAMESPACES: ")
            for i in namespaces:
                self.log.info(i)
            contexts = [context['name'] for context in contexts]
            active_context = active_context['name']
            delete_list = []
            admin_list = []

            self.log.info("Current context: ", active_context)

            self.log.info("Inside delete list if")
            for i in range(len(contexts)):
                try:
                    self.log.info("INSIDE TRY")
                    config.load_kube_config(context=contexts[i])
                    api_instance = client.CoreV1Api()
                    api_response = api_instance.list_namespaced_pod(namespace=namespaces[i], timeout_seconds=10)
                    delete_list.append("False")
                except:
                    self.log.info("INSIDE EXCEPT")
                    delete_list.append("True")


            for i in range(len(contexts)):
                try:
                    self.log.info("INSIDE TRY")
                    config.load_kube_config(context=contexts[i])
                    api_instance = client.CoreV1Api()
                    api_response = api_instance.list_namespaced_pod(namespace='kube-system', timeout_seconds=10)
                    admin_list.append("True")
                except:
                    self.log.info("INSIDE EXCEPT")
                    admin_list.append("False")
        
            self.log.info("DELETE LIST: ")
            for i in delete_list:
                self.log.info(i)
            self.log.info("TEST STATEMENT")

            self.send({
                'msgtype': 'context-select',
                'contexts': contexts,
                'active_context': active_context,
                'clusters': clusters,
                'current_cluster': current_cluster,
                'delete_list': delete_list,
                'admin_list': admin_list,
            })

    def check_config(self, cluster, namespace, svcaccount):
        # def run_command(command):
        #     p = subprocess.Popen(command,
        #                         stdout=subprocess.PIPE,
        #                         stderr=subprocess.STDOUT)
        #     return iter(p.stdout.readline, b'')


        with io.open(os.environ['HOME'] + '/.kube/config', 'r', encoding='utf8') as stream:
                load = yaml.safe_load(stream)
                self.log.info(load)
        
        for i in load['clusters']:
            if i['name'] == cluster:
                server_host = i['cluster']['server']
        
        kubeconfig = os.environ['HOME'] + "/config"
        os.environ['KUBECONFIG'] = kubeconfig
        os.environ['NAMESPACE'] = namespace
        os.environ['SERVICE_ACCOUNT'] = svcaccount
        os.environ['SERVER'] = server_host
        os.environ['CLUSTER'] = cluster

        error = ''
        # for line in run_command(command):
        #     print(line)
        output = subprocess.call('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test.sh', shell=True)
        self.log.info("output: ", output)
        if output != 0:
            error = 'Error'

        if error == '':
            output2 = subprocess.call('/Users/sahiljajodia/SWAN/switch-cluster/switch-cluster/test2.sh', shell=True)
            if output2 != 0:
                self.send({
                'msgtype': 'authentication-unsuccessfull',
                'error': "Error"
                })
            else:
                self.send({
                'msgtype': 'authentication-successfull',
                })
        else:
            self.send({
            'msgtype': 'authentication-unsuccessfull',
            'error': error
            })

        


def load_ipython_extension(ipython):
    """ Load Jupyter kernel extension """

    log = logging.getLogger('tornado.switchcluster.kernelextension')
    log.name = 'switchcluster.kernelextension'
    log.setLevel(logging.INFO)
    log.propagate = True

    if ipykernel_imported:
        if not isinstance(ipython, zmqshell.ZMQInteractiveShell):
            log.error("SwitchCluster: Ipython not running through notebook. So exiting.")
            return
    else:
        return

    log.info("Starting SwitchCluster Kernel Extension")
    ext = SwitchCluster(ipython, log)
    ext.register_comm()