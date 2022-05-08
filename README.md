# portainer-swarm-migrate
A tool to automatically migrate orphaned portainer swarm stacks into a new cluster. 

If you've ever needed to restart your docker swarm, and portainer isn't showing your old stacks on the new cluster, then this tool will help you automatically migrate them over without needing to manually stand them back up again. 

## Requirements
* requests

## Installation

```bash
git clone https://github.com/mattstruble/portainer-swarm-migrate.git
cd portainer-swarm-migrate; mv configuration.cfg.example configuration.cfg
```

## Setup 

1. Update the `configuration.cfg` file with your Portainer admin credentials and the public http IP address and port. **It is important that the url is the PUBLIC address so that the tool can query the REST API**. 
2. Add your new cluster swarm ID as the `clusterID` field. 
   * This can be found by executing `sudo docker info` on one of your swarm nodes and looking for the `ClusterID` value. 

## Usage

The purpose of this script is to automatically migrate orphaned docker swarm stacks onto a new swarm cluster. The script is designed to automatically locate orphaned stacks via the portainer HTTP REST API. 

By running `python migrate.py` the tool will perform the following steps automatically:
1. Query the Portainer instance and locate any stack that isn't associated with the configured ClusterID
2. It will stop any stack that is running on the old swarm
3. Once the stacks have stopped it will migrate them to the new swarm and start them back up again

The end result should be all of your old stacks automatically migrated to the new swarm instance. 
