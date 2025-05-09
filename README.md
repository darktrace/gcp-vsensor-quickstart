# Darktrace vSensor Quickstart for GCP

> [!IMPORTANT]
> GCP Deployment Manager, which this Quick Start uses, is [deprecated and will reach end of support on December 31, 2025](https://cloud.google.com/deployment-manager/docs/deprecations).
> We recommend all customers redeploy their vSensor deployments using the [Darktrace GCP vSensor Terraform Module](https://github.com/darktrace/terraform-gcp-vsensor), which can be used with [GCP Infrastructure Manager](https://cloud.google.com/infrastructure-manager/docs/overview). An in-place migration from Deployment Manager to Infrastructure Manager is not possible.
>
> Existing vSensor deployments using Deployment Manager will continue running past this date, but updating or destroying all resources will need to be done manually.

## Introduction

This Quick Start deploys Darktrace vSensor virtual threat detection on Google Cloud Platform. Instead of relying on flow logs, Darktrace probes analyze raw data from mirrored virtual private cloud (VPC) traffic to learn to identify threats. This guide covers the steps necessary to deploy this Quick Start.

GCP Virtual Private Cloud (VPC) Packet Mirroring copies traffic from Computing Engine instances you want to monitor. A Load Balancer distributes mirrored traffic to Darktrace vSensor probes in a private subnet. The deployment also supports sending data to vSensors from Darktrace osSensors you configure on virtual machines and containerized applications.

Darktrace vSensor stores PCAP data from mirrored traffic and stores it in a Google Storage bucket for later recall from the Threat Visualizer.

## Architecture

![Architecture Diagram](architecture_diagram.png)

The GCP Darktrace vSensor Quick Start deploys the following:

- (Optional) A VPC, or provide an existing VPC to deploy into
- A Subnet for containing the internal vSensors
- A Cloud Router to provide vSensors with appliance / update connectivity
- A Managed Instance Group containing vSensors with predictive autoscaling
- (Optional) A GCP Storage bucket for storing PCAPS for later analysis
- (Optional) A Bastion subnet and host for allowing external access to the vSensors
- An Internal TCP Load balancer with automatic Packet Mirroring for the Bastion
- Load balancer frontend as a Packet Mirroring Collector
- (Optional) Packet Mirroring policies for existing subnets
- (Optional) Load balancer frontend for osSensor support
- IAM role assignments configuring GCP Ops Agent logging and (optionally) storage bucket
- Firewall rules for allowing packet mirroring, external bastion access and SSH-in-browser via IAP
- (Optional) User and public ssh key for ssh public key authentication

## Requirements

### Enabled APIs
The following GCP APIs are required for deploying this template:

- Compute Engine
- Deployment Manager v2
- Identity and Access Management (IAM)
- IAM Service Account Credentials
- Cloud Resource Manager
- Cloud Logging
- Cloud Monitoring

### IAM Roles
It is recommended that a project owner deploys the template in the respective project.

Furthermore, the "Google APIs Service Agent" IAM principal (in the form of `<PROJECT_ID>@cloudservices.gserviceaccount.com`) in the deployment project requires an additional role to apply the vSensor service account it's own rules:

- resourcemanager.projects.setIamPolicy

This may be achieved by setting this principal as `Owner` of the project, but applying the role manually instead is well advised.

### Traffic Ingestion

**Please note that the template uses regional resources, it is necessary for separate deployments using separate Probe Push Tokens per region.**

Traffic can be ingested for analysis by Darktrace using a combination of two methods:

- [Packet Mirroring](https://cloud.google.com/vpc/docs/packet-mirroring)
- Installing Darktrace osSensors on compatible instances

In both cases, extra configuration is required to permit access from mirrored resources to the Quick Start deployment using VPC peering / other routing.

## Deploying the Quick Start

This Quick Start can be deployed using the `gcloud` command line utility which can be installed and configured using instructions [here](https://cloud.google.com/sdk/docs/install-sdk). Make sure to select the correct project you wish to deploy the Quick Start into.

A sample configuration file `launch.yaml` is provided. Fill this with configuration parameters, using `launch.py.schema` for further information about the available parameters.

Create a new deployment with:

`gcloud deployment-manager deployments create <YOUR_DEPLOYMENT_NAME> --config launch.yaml`

If you need to correct a parameter/update the deployment, some changes may be possible by updating the template:

`gcloud deployment-manager deployments update <YOUR_DEPLOYMENT_NAME> --config launch.yaml`

The deployment can be deleted with:

`gcloud deployment-manager deployments delete <YOUR_DEPLOYMENT_NAME>`

**Please note, deleting the deployment requires:**
- removing temporary holds on files in the `keys` directory and retention settings to empty the PCAP bucket
- removing any additional packet mirroring sessions and frontend (forwarding rules) created outside the template

### Configuration Options

The Quick Start can be deployed into a new VPC it creates automatically, or the `existing-vpc-name` parameter can be set to deploy into new subnets within an existing VPC in your project. 

A bastion host can be configured optionally using the `bastion-enable` boolean parameter. If you already have access to your resources via some other means, or only wish to use SSH-in-browser/IAP, this can be disabled.

If the `ossensor-hmac` parameter is not given, osSensors will not be able to register with the deployment. **This cannot be changed later without redeploying entirely.**

Setting the configured instance size, scaling counts, PCAP storage retention and ultimately the mirrored traffic bandwidth will affect the ongoing deployment cost.

Many regions have GCP Storage bucket support, whenever possible this Quick Start will pick this region to reduce PCAP data transfer costs.
In cases where the vSensor region does not have an exact match with a GCP Storage region, this template will choose another as close as possible.

The bastion (if enabled) and the vSensor can be configured optionally with user and ssh public key for ssh public key authentication using the `bastion-ssh-user-key` and the `mig-ssh-user-key` variables.

Packet mirroring can be configured for existing subnets in an existing VPC you are deploying into. Provide subnet names comma separated in the `subnets-to-mirror` variable.

If you wish to allow traffic mirroring of IPv6 traffic from subnets or hosts, set `ipv6-enable` true. The same packet mirror collector is used for both IPv4 and IPv6.

Consider reviewing:
- https://cloud.google.com/compute/vm-instance-pricing
- https://cloud.google.com/storage/pricing

### Upgrading to vSensor 6.3

The vSensor 6.3 release includes an updated base OS image. If you have an existing pre-6.3 deployment of this Quick Start running, you will need to update it.

To do this:
1. Update your existing copy of this Quick Start with the latest version (`git pull` or similar)
2. In your `launch.yaml`, set the `vsensor-63-upgrade-in-progress: true` parameter
3. Run `gcloud deployment-manager deployments update <YOUR_DEPLOYMENT_NAME> --config launch.yaml`
4. Wait for the Managed Instance Group to start using the new template
5. Set the `vsensor-63-upgrade-in-progress` parameter to `false` (or remove it)
6. Run `gcloud deployment-manager deployments update` again

## Post deployment

### Confirming Operation

Once deployment has been successfully completed:

- Wait a few minutes for the vSensor instances to install and configure themselves.
- Confirm a vSensor has appeared in System Status of your Appliance Threat Visualizer using the dedicated Push Token you used in the deployment.
- Follow the guide below to configure osSensor / packet mirroring sessions and check they appear in the threat visualizer after a few minutes.

### Template Outputs

This deployment template provides outputs to ease configuration of osSensors and packet mirroring. These can be accessed by:

- Go to [Deployment Mananger](https://console.cloud.google.com/dm/deployments/) in the GCP Console.
- Clicking on the deployment name.
- Click the Layout `View` link.
- Outputs will be listed with `finalValue` keys at the top of the resulting layout.


These outputs include:
- The IP address of the vSensor load balancer to configure osSensors for. You will need to configure any VPC peering/routing to allow osSensor instances to access the vSensor subnet provided, which includes this IP.
- The subnet CIDR for easy reference of the above.
- The PCAP bucket name, to confirm the vSensors are writing to it. Each vSensor will create a numerical directory (its Compute Engine Instance ID) once it receieves mirroring traffic.
- Created VPC and subnet names.

### Packet Mirroring

To configure packet mirroring sessions extra to the `subnets-to-mirror` defined above, you must create a further [packet mirroring policy](https://console.cloud.google.com/networking/packetmirroring) to the provided packet mirror collector.

** NOTE: ** IPv6 support (if enabled above) also requires the packet filter to be changed during the policy creation to allow IPv6 traffic.

### Logging / Metrics

Google Ops Agent is configured on the vSensors and bastion automatically to provide more detailed statistics including CPU, memory and bandwidth.

It also provides [Log Explorer](https://console.cloud.google.com/logs/) logs in four 'Log Name' groups for supporting debugging:
- `vsensor-syslog` For general syslog logging.
- `vsensor-updates` For logging from apt/dpkg package updating of the vSensor and OS packages.
- `vsensor-services` For logging from the main vSensor product components.
- `vsensor-userdata` For logging from the initial vSensor installation.

### Support

Please use the [Darktrace Customer Portal](https://customerportal.darktrace.com) to request support in using this template.

For issues during initial installation, provide any GCP Deployment Manager errors and `vsensor-userdata` (see previous section). 
