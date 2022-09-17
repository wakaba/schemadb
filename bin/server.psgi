#!/usr/bin/perl
use strict;
use warnings;

$SIG{PIPE} = 'IGNORE';

return sub {
  delete $SIG{CHLD} if defined $SIG{CHLD} and not ref $SIG{CHLD}; # XXX

  my $http = Wanage::HTTP->new_from_psgi_env ($_[0]);
  my $app = Warabe::App->new_from_http ($http);

  return $app->execute_by_promise (sub {
    return $app->send_redirect
        ('https://suika.suikawiki.org/gate/2007/schema/schema' . $app->http->url->{path},
         status => 301);
  });
};
