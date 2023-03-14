# Constellation Network
### nodectl `v2.0.0`

## Description
Constellation Network's **nodect** was created and designed by **Constellation Network** to **simplify** and pull out the complexity associated with running a **Constellation Network Validator Node**.  

It is easy to *say* that a Node for any project is simple to deploy, just takes a little eblow grease and away you go!  However, the truth is; unless you have technical know how, no matter what simplistic tools are presented, there will be learning curves, trial and error, and some requirement to pay attention to detail.

With this in mind, **nodectl** was created to take a true **Systems and Site Reliability Engineering** out of the requirements to run a **Node**; morevoer, **nodectl** is designed to help you build your Node, run your Node, and administer your Node, with extensive documentation, help commands, and **community backing**. **nodectl** can be a powerful **utility** to help ease your journey to being a **Constellation Network Node Operator** and **datapenuer**. 

## Usage

Extensive help has been written up and offered through [Constellation Network's Documenation hub](https://docs.constellationnetwork.io/).  

*In order to avoid making necessary updates in muliple locations, this open source project's documentataion pertaining to the operations of use of nodectl will be present on Constellation Networks' Documentation Hub:*
  - installation
  - upgrade
  - configuration
  - operation

## Internals
**nodectl** is written [currently] in Python3.  It is a combination of object oritentation and functional programming.  **nodectl** is integrated into three components main components.

#### Core Components
- core functionality
- configurator
- automation (`auto_restart`)

```mermaid
flowchart TD
  A[Core Functionality];
  B[Configurator];
  C[Migrator];
  D[Automation];
  E[cn-config.yaml];
  B <--> C;
  D <--> A;
  E --> B <--> A;
```


