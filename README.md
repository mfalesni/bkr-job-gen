bkr-job-gen
===========

Do you want to generate Beaker jobs from simple JSON template? You're on the right place ...

Introduction:
=============
Hello you brave humans who are trying to use this little script written by me.

Let's start with talking about how does it work. It typically does 3 steps:

1. Load JSON template into internal representation
2. Modify/add/delete some parameters in this internal representation by commands specified as parameters for this script
3. Print XML out.

It should be able to do more things in close future, but it does only these things for now.

Synopsis (main):
================
./bkr_job_gen.py <command1> <command2> ... <commandN>

Synopsis (command):
===================

    load <json-file> ### Load JSON template
    print ### Print out the XML
    kickstart <file-with-kickstart> ### Attach kickstart file for specified recipe
    recipe <seq. # of recipe in recipeset> ### Select recipe from recipeset for next operations, default 0 (first recipe)
    task <task-name> ### Select task with specified name in selected recipe for next operations
    param set|delete <task-param-name> [param-value if set] ### Change parameters passed to tasks
    requires host|distro <req-name> set|delete [req-value if set] (format of req-value is: "<op><value>", so f.e. "=RHEL-6.3" or ">4096") ### This speaks for itself, but when using "distro", you don't have to write the "distro" or "distro_" prefix

Examples:
=========

./bkr_job_gen.py load job.json task "/CloudForms/Installation/CloudEngine" param set YUM_RELEASEVER 6.2 task "/distribution/reservesys" param set RESERVETIME 2d recipe 0 (<- this command isn't actually needed, as it is 0 by default) kickstart kickstart.txt requires host hostname set "troll.pc.com" print

Commands task and recipe don't have to be specified every time using them-dependent commands (param, requires, ...), they are simply valid until overrided with next task or recipe command. Imagine them as simple variables you have available. When you issue load command, all changes you made before are lost and you're starting from clean loaded template.

IMPORTANT THING!!! This thing works only pre-made JSON templates, it can't generate new XML from nothing. I decided to make it this way because:

1. JSON is much simpler than XML
2. Tasks used inside some testing suite usually have many common parameters, so it's better to have some basic stuff you can modify (inheritance -> good practice )

Issues:
=======
- requires delete doesn't work yet, working on it