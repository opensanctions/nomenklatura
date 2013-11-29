
Vagrant.configure("2") do |config|
  config.vm.box = "raring"
  config.vm.box_url = "http://goo.gl/y79mW"
  config.vm.hostname = "nomenklatura"
  config.vm.network :forwarded_port, guest: 5000, host: 5000

  # config.vm.provider :virtualbox do |vb|
  #   # Use VBoxManage to customize the VM. For example to change memory:
  #   vb.customize ["modifyvm", :id, "--memory", "1024"]
  # end

  config.vm.provision :shell, :privileged => false, :path => 'contrib/vagrant-install.sh'
end
