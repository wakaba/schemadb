use Storable qw(retrieve);
use Data::Dumper;

my $file_name = shift or die;

my $data = retrieve $file_name;
print Dumper $data;
